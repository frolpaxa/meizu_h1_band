#!/usr/bin/env python3
"""Test Xiaomi authentication against Meizu H1."""
import asyncio
from bleak import BleakClient, BleakScanner
from Crypto.Cipher import AES

# Handles from the diagnostic report.
WRITE_HANDLE = 25   # 0000fec7 (write)
AUTH_HANDLE = 29    # 0000fea1 (indicate/read)

# Xiaomi Pairing v1 commands.
CMD_SEND_KEY = 0x01
CMD_REQUEST_RANDOM = 0x02
CMD_SEND_ENCRYPTED = 0x03


async def test_auth(address: str, auth_key_hex: str):
    key = bytes.fromhex(auth_key_hex.replace(" ", ""))
    print(f"[*] Key: {key.hex()} ({len(key)} bytes)")
    
    cipher = AES.new(key, AES.MODE_ECB)
    responses = asyncio.Queue()
    
    def callback(char, data):
        raw = bytes(data)
        print(f"[>] Response: {raw.hex()}")
        responses.put_nowait(raw)
    
    device = await BleakScanner.find_device_by_address(address, timeout=20)
    if not device:
        print("[!] Device not found")
        return
    
    async with BleakClient(device) as client:
        print(f"[+] Connected: {device.name}")
        
        auth_char = client.services.get_characteristic(AUTH_HANDLE)
        write_char = client.services.get_characteristic(WRITE_HANDLE)
        
        if not auth_char or not write_char:
            print("[!] Characteristics not found")
            return
        
        await client.start_notify(auth_char, callback)
        
        try:
            # Step 1: send key.
            print("[*] Step 1: Sending key...")
            await client.write_gatt_char(write_char, bytes([CMD_SEND_KEY]) + key)
            await asyncio.sleep(1)
            
            # Step 2: request random value.
            print("[*] Step 2: Requesting random value...")
            await client.write_gatt_char(write_char, bytes([CMD_REQUEST_RANDOM]))
            
            try:
                response = await asyncio.wait_for(responses.get(), timeout=5)
            except asyncio.TimeoutError:
                print("[!] Timed out. The band did not respond.")
                return
            
            # Check the response.
            if len(response) >= 17 and response[0] == CMD_REQUEST_RANDOM:
                challenge = response[1:17]
                print(f"[*] Challenge received: {challenge.hex()}")
                
                # Step 3: send the encrypted response.
                encrypted = cipher.encrypt(challenge)
                print(f"[*] Step 3: Sending encrypted response: {encrypted.hex()}")
                await client.write_gatt_char(write_char, bytes([CMD_SEND_ENCRYPTED]) + encrypted)
                
                try:
                    confirm = await asyncio.wait_for(responses.get(), timeout=5)
                    print(f"[+] Final response: {confirm.hex()}")
                    if confirm[0] == 0x10:
                        print("[+] AUTHENTICATION SUCCEEDED!")
                    else:
                        print(f"[-] Unexpected response: cmd={confirm[0]:02x}")
                except asyncio.TimeoutError:
                    print("[-] No final confirmation")
            else:
                print(f"[-] Unexpected response format: {response.hex()}")
                print("    Expected: cmd=0x02 + 16-byte challenge")
                
        finally:
            await client.stop_notify(auth_char)


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("Usage: python test_auth.py <ADDRESS> <AUTH_KEY_HEX>")
        sys.exit(1)
    asyncio.run(test_auth(sys.argv[1], sys.argv[2]))
