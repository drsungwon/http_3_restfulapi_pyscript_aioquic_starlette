import asyncio

from lib.http3_server import http3_server_configuration, http3_server_main

if __name__ == "__main__":
    args, configuration, asgi_handler = http3_server_configuration()

    print('server activated ...')
    print('ip address   : {}'.format(args.host))
    print('port number  : {}'.format(args.port))
    print('certificate  : {}'.format(args.certificate))
    print('private key  : {}'.format(args.private_key))
    print('asgi handler : {}'.format(asgi_handler))

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

# python server.py -c cert/localhost.crt -k cert/localhost.key server_app:run