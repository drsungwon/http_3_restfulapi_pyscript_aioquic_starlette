import argparse
import asyncio
import importlib
import logging
import time
from collections import deque
from email.utils import formatdate
from typing import Callable, Deque, Dict, List, Optional, Union, cast

import aioquic
from aioquic.asyncio import QuicConnectionProtocol, serve
from aioquic.h0.connection import H0_ALPN, H0Connection
from aioquic.h3.connection import H3_ALPN, H3Connection
from aioquic.h3.events import (
    DatagramReceived,
    DataReceived,
    H3Event,
    HeadersReceived,
    WebTransportStreamDataReceived,
)
from aioquic.h3.exceptions import NoAvailablePushIDError
from aioquic.quic.configuration import QuicConfiguration
from aioquic.quic.events import DatagramFrameReceived, ProtocolNegotiated, QuicEvent
from aioquic.quic.logger import QuicFileLogger
from aioquic.tls import SessionTicket

try:
    import uvloop
except ImportError:
    uvloop = None

AsgiApplication = Callable
HttpConnection = Union[H0Connection, H3Connection]

SERVER_NAME = "aioquic/" + aioquic.__version__

AsgiApplicationHandler = None # modified by drsungwon

class HttpRequestHandler:
    def __init__(
        self,
        *,
        authority: bytes,
        connection: HttpConnection,
        protocol: QuicConnectionProtocol,
        scope: Dict,
        stream_ended: bool,
        stream_id: int,
        transmit: Callable[[], None],
    ) -> None:
        self.authority = authority
        self.connection = connection
        self.protocol = protocol
        self.queue: asyncio.Queue[Dict] = asyncio.Queue()
        self.scope = scope
        self.stream_id = stream_id
        self.transmit = transmit

        if stream_ended:
            self.queue.put_nowait({"type": "http.request"})

    def http_event_received(self, event: H3Event) -> None:
        if isinstance(event, DataReceived):
            self.queue.put_nowait(
                {
                    "type": "http.request",
                    "body": event.data,
                    "more_body": not event.stream_ended,
                }
            )
        elif isinstance(event, HeadersReceived) and event.stream_ended:
            self.queue.put_nowait(
                {"type": "http.request", "body": b"", "more_body": False}
            )

    async def run_asgi(self, app: AsgiApplication) -> None:
        await app(self.scope, self.receive, self.send)

    async def receive(self) -> Dict:
        return await self.queue.get()

    async def send(self, message: Dict) -> None:
        if message["type"] == "http.response.start":
            self.connection.send_headers(
                stream_id=self.stream_id,
                headers=[
                    (b":status", str(message["status"]).encode()),
                    (b"server", SERVER_NAME.encode()),
                    (b"date", formatdate(time.time(), usegmt=True).encode()),
                ]
                + [(k, v) for k, v in message["headers"]],
            )
        elif message["type"] == "http.response.body":
            self.connection.send_data(
                stream_id=self.stream_id,
                data=message.get("body", b""),
                end_stream=not message.get("more_body", False),
            )
        elif message["type"] == "http.response.push" and isinstance(
            self.connection, H3Connection
        ):
            request_headers = [
                (b":method", b"GET"),
                (b":scheme", b"https"),
                (b":authority", self.authority),
                (b":path", message["path"].encode()),
            ] + [(k, v) for k, v in message["headers"]]

            # send push promise
            try:
                push_stream_id = self.connection.send_push_promise(
                    stream_id=self.stream_id, headers=request_headers
                )
            except NoAvailablePushIDError:
                return

            # fake request
            cast(HttpServerProtocol, self.protocol).http_event_received(
                HeadersReceived(
                    headers=request_headers, stream_ended=True, stream_id=push_stream_id
                )
            )
        self.transmit()

class HttpServerProtocol(QuicConnectionProtocol):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._handlers: Dict[int, HttpRequestHandler] = {}
        self._http: Optional[HttpConnection] = None

    def http_event_received(self, event: H3Event) -> None:
        if isinstance(event, HeadersReceived) and event.stream_id not in self._handlers:
            authority = None
            headers = []
            http_version = "0.9" if isinstance(self._http, H0Connection) else "3"
            raw_path = b""
            method = ""
            protocol = None
            for header, value in event.headers:
                if header == b":authority":
                    authority = value
                    headers.append((b"host", value))
                elif header == b":method":
                    method = value.decode()
                elif header == b":path":
                    raw_path = value
                elif header == b":protocol":
                    protocol = value.decode()
                elif header and not header.startswith(b":"):
                    headers.append((header, value))

            if b"?" in raw_path:
                path_bytes, query_string = raw_path.split(b"?", maxsplit=1)
            else:
                path_bytes, query_string = raw_path, b""
            path = path_bytes.decode()
            self._quic._logger.info("HTTP request %s %s", method, path)

            # FIXME: add a public API to retrieve peer address
            client_addr = self._http._quic._network_paths[0].addr
            client = (client_addr[0], client_addr[1])

            extensions: Dict[str, Dict] = {}
            if isinstance(self._http, H3Connection):
                extensions["http.response.push"] = {}
            scope = {
                "client": client,
                "extensions": extensions,
                "headers": headers,
                "http_version": http_version,
                "method": method,
                "path": path,
                "query_string": query_string,
                "raw_path": raw_path,
                "root_path": "",
                "scheme": "https",
                "type": "http",
            }
            handler = HttpRequestHandler(
                authority=authority,
                connection=self._http,
                protocol=self,
                scope=scope,
                stream_ended=event.stream_ended,
                stream_id=event.stream_id,
                transmit=self.transmit,
            )
            self._handlers[event.stream_id] = handler
            asyncio.ensure_future(handler.run_asgi(AsgiApplicationHandler))
        elif (
            isinstance(event, (DataReceived, HeadersReceived))
            and event.stream_id in self._handlers
        ):
            handler = self._handlers[event.stream_id]
            handler.http_event_received(event)
        elif isinstance(event, DatagramReceived):
            handler = self._handlers[event.stream_id]
            handler.http_event_received(event)
        elif isinstance(event, WebTransportStreamDataReceived):
            handler = self._handlers[event.session_id]
            handler.http_event_received(event)

    def quic_event_received(self, event: QuicEvent) -> None:
        if isinstance(event, ProtocolNegotiated):
            if event.alpn_protocol in H3_ALPN:
                self._http = H3Connection(self._quic, enable_webtransport=True)
            elif event.alpn_protocol in H0_ALPN:
                self._http = H0Connection(self._quic)
        elif isinstance(event, DatagramFrameReceived):
            if event.data == b"quack":
                self._quic.send_datagram_frame(b"quack-ack")

        #  pass event to the HTTP layer
        if self._http is not None:
            for http_event in self._http.handle_event(event):
                self.http_event_received(http_event)


class SessionTicketStore:
    """
    Simple in-memory store for session tickets.
    """

    def __init__(self) -> None:
        self.tickets: Dict[bytes, SessionTicket] = {}

    def add(self, ticket: SessionTicket) -> None:
        self.tickets[ticket.ticket] = ticket

    def pop(self, label: bytes) -> Optional[SessionTicket]:
        return self.tickets.pop(label, None)

def http3_server_configuration():
    defaults = QuicConfiguration(is_client=False)

    parser = argparse.ArgumentParser(description="QUIC server")
    parser.add_argument(
        "app",
        type=str,
        nargs="?",
        default="demo:app",
        help="the ASGI application as <module>:<attribute>",
    )
    parser.add_argument(
        "-c",
        "--certificate",
        type=str,
        required=True,
        help="load the TLS certificate from the specified file",
    )
    parser.add_argument(
        "--congestion-control-algorithm",
        type=str,
        default="reno",
        help="use the specified congestion control algorithm",
    )
    parser.add_argument(
        "--host",
        type=str,
        default="::",
        help="listen on the specified address (defaults to ::)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=4433,
        help="listen on the specified port (defaults to 4433)",
    )
    parser.add_argument(
        "-k",
        "--private-key",
        type=str,
        help="load the TLS private key from the specified file",
    )
    parser.add_argument(
        "-l",
        "--secrets-log",
        type=str,
        help="log secrets to a file, for use with Wireshark",
    )
    parser.add_argument(
        "--max-datagram-size",
        type=int,
        default=defaults.max_datagram_size,
        help="maximum datagram size to send, excluding UDP or IP overhead",
    )
    parser.add_argument(
        "-q",
        "--quic-log",
        type=str,
        help="log QUIC events to QLOG files in the specified directory",
    )
    parser.add_argument(
        "--retry",
        action="store_true",
        help="send a retry for new connections",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="increase logging verbosity"
    )
    args = parser.parse_args()

    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        level=logging.DEBUG if args.verbose else logging.INFO,
    )
    
    # import ASGI application
    module_str, attr_str = args.app.split(":", maxsplit=1)
    module = importlib.import_module(module_str)

    global AsgiApplicationHandler
    AsgiApplicationHandler = getattr(module, attr_str)

    # create QUIC logger
    if args.quic_log:
        quic_logger = QuicFileLogger(args.quic_log)
    else:
        quic_logger = None

    # open SSL log file
    if args.secrets_log:
        secrets_log_file = open(args.secrets_log, "a")
    else:
        secrets_log_file = None

    configuration = QuicConfiguration(
        alpn_protocols=H3_ALPN + H0_ALPN + ["siduck"],
        congestion_control_algorithm=args.congestion_control_algorithm,
        is_client=False,
        max_datagram_frame_size=65536,
        max_datagram_size=args.max_datagram_size,
        quic_logger=quic_logger,
        secrets_log_file=secrets_log_file,
    )

    # load SSL certificate and key
    configuration.load_cert_chain(args.certificate, args.private_key)

    if uvloop is not None:
        uvloop.install()

    return args, configuration, module_str + ':' + attr_str

async def http3_server_main(
    host: str,
    port: int,
    configuration: QuicConfiguration,
    retry: bool,
) -> None:
    session_ticket_store = SessionTicketStore()
    await serve(
        host,
        port,
        configuration=configuration,
        create_protocol=HttpServerProtocol,
        session_ticket_fetcher=session_ticket_store.pop,
        session_ticket_handler=session_ticket_store.add,
        retry=retry,
    )
    await asyncio.Future()

if __name__ == "__main__":

    args, configuration, asgi_handler = http3_server_configuration()

    try:
        asyncio.run(
            http3_server_main(
                host=args.host,
                port=args.port,
                configuration=configuration,
                retry=args.retry,
            )
        )
    except KeyboardInterrupt:
        pass
