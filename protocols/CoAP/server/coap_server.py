import asyncio
import aiocoap.resource as resource
import aiocoap

from common.file_manager import save_file
from common.integrity_checker import sha256

class BinaryUploadResource(resource.Resource):

    @staticmethod
    async def render_put(request):
        filename          = "unknown.bin"
        expected_checksum = None

        for query in request.opt.uri_query:
            # split("=", 1) so filenames containing "=" are handled correctly
            if query.startswith("file="):
                filename = query.split("=", 1)[1]
            elif query.startswith("checksum="):
                expected_checksum = query.split("=", 1)[1]

        print(f"--- CoAP: Receiving '{filename}' ({len(request.payload)} bytes) ---")

        actual_checksum = sha256(request.payload)

        if expected_checksum and actual_checksum != expected_checksum:
            print(f"Checksum mismatch for {filename}!")
            return aiocoap.Message(
                code=aiocoap.BAD_REQUEST,
                payload=b"checksum mismatch",
            )

        save_file(filename, data=request.payload)

        return aiocoap.Message(code=aiocoap.CHANGED, payload=b"OK")


async def main():
    root = resource.Site()
    root.add_resource(["upload"], BinaryUploadResource())

    print("CoAP Server starting on UDP 5683 (Blockwise enabled)...")
    await aiocoap.Context.create_server_context(root, bind=("0.0.0.0", 5683))

    await asyncio.get_running_loop().create_future()


if __name__ == "__main__":
    asyncio.run(main())