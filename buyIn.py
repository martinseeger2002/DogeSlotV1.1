import configparser
from bitcoinrpc.authproxy import AuthServiceProxy, JSONRPCException
from decimal import Decimal
from ecdsa import SigningKey, SECP256k1, util
import hashlib
import struct
import base58

# Load RPC credentials from RPC.conf
config = configparser.ConfigParser()
config.read('RPC.conf')

rpc_user = config['rpcconfig']['rpcuser']
rpc_password = config['rpcconfig']['rpcpassword']
rpc_host = config['rpcconfig']['rpchost']
rpc_port = config['rpcconfig']['rpcport']

# Create a connection to the Dogecoin RPC server
def create_rpc_connection():
    return AuthServiceProxy(f"http://{rpc_user}:{rpc_password}@{rpc_host}:{rpc_port}")

rpc_connection = create_rpc_connection()

# Define the recipient address
recipient_address = "<pool_address>"

# Helper functions
def wif_to_privkey_hex(wif):
    # Decode WIF to get private key
    private_key_full = base58.b58decode_check(wif)
    # Remove version byte and compression flag
    private_key_bytes = private_key_full[1:-1]
    return private_key_bytes.hex()

def wif_to_address(wif_privkey):
    private_key_full = base58.b58decode_check(wif_privkey)
    # Remove version byte and compression flag
    private_key_bytes = private_key_full[1:-1]
    privkey = SigningKey.from_string(private_key_bytes, curve=SECP256k1)
    vk = privkey.get_verifying_key()
    public_key_bytes = b'\x02' + vk.to_string()[0:32]  # Compressed public key

    # Perform SHA256 hashing on the public key
    sha256 = hashlib.sha256(public_key_bytes).digest()
    # Perform RIPEMD-160 hashing on the result
    ripemd160 = hashlib.new('ripemd160', sha256).digest()
    # Add version byte (0x1E for Dogecoin mainnet)
    versioned_payload = b'\x1E' + ripemd160
    # Perform double SHA256 hashing on the versioned payload
    checksum = hashlib.sha256(hashlib.sha256(versioned_payload).digest()).digest()[:4]
    # Concatenate versioned payload and checksum
    address_bytes = versioned_payload + checksum
    # Convert to Base58Check format
    return base58.b58encode(address_bytes).decode('utf-8')

def varint(n):
    if n < 0xfd:
        return struct.pack('<B', n)
    elif n <= 0xffff:
        return b'\xfd' + struct.pack('<H', n)
    elif n <= 0xffffffff:
        return b'\xfe' + struct.pack('<I', n)
    else:
        return b'\xff' + struct.pack('<Q', n)

def get_utxos(address):
    """
    Retrieve UTXOs for the given address using Dogecoin Core RPC.
    """
    global rpc_connection
    utxos = []

    try:
        # Get the list of unspent transaction outputs for the address
        utxos_list = rpc_connection.listunspent(1, 9999999, [address])
        for utxo in utxos_list:
            utxo_info = {
                'txid': utxo['txid'],
                'vout': utxo['vout'],
                'amount': int(Decimal(str(utxo['amount'])) * Decimal('1e8')),  # Convert DOGE to satoshis
                'scriptPubKey': utxo['scriptPubKey'],
            }
            utxos.append(utxo_info)
    except JSONRPCException as e:
        print(f"An error occurred while retrieving UTXOs: {e.error['message']}")

    return utxos

def create_script_pubkey(address):
    # Decode the address
    address_bytes = base58.b58decode_check(address)
    # The first byte is the version, the rest is the pubkey hash
    pubkey_hash = address_bytes[1:]
    # Build the scriptPubKey
    script_pubkey = (
        b'\x76' +  # OP_DUP
        b'\xa9' +  # OP_HASH160
        bytes([len(pubkey_hash)]) +
        pubkey_hash +
        b'\x88' +  # OP_EQUALVERIFY
        b'\xac'    # OP_CHECKSIG
    )
    return script_pubkey.hex()

def create_raw_transaction(utxos, from_address, to_address, amount_satoshis, fee_satoshis):
    inputs = []
    outputs = []
    total_input = 0

    # Select UTXOs to cover the amount + fee
    for utxo in utxos:
        inputs.append({
            'txid': utxo['txid'],
            'vout': utxo['vout'],
            'scriptPubKey': utxo['scriptPubKey'],  # Needed for signing
            'amount': utxo['amount'],  # in satoshis
        })
        total_input += utxo['amount']
        if total_input >= amount_satoshis + fee_satoshis:
            break

    if total_input < amount_satoshis + fee_satoshis:
        print("Insufficient funds.")
        return None

    # Outputs
    # Recipient output
    outputs.append({
        'address': to_address,
        'amount': amount_satoshis,  # in satoshis
    })

    # Change output (if any)
    change_satoshis = total_input - amount_satoshis - fee_satoshis
    if change_satoshis > 0:
        outputs.append({
            'address': from_address,
            'amount': change_satoshis,
        })

    # Build the transaction object
    tx = {
        'version': 1,
        'locktime': 0,
        'inputs': inputs,
        'outputs': outputs,
    }

    return tx

def serialize_transaction(tx, for_signing=False, input_index=None, script_code=None):
    # Start with the version
    result = struct.pack("<I", tx['version'])  # version

    # Serialize inputs
    result += varint(len(tx['inputs']))  # Number of inputs

    for i, txin in enumerate(tx['inputs']):
        result += bytes.fromhex(txin['txid'])[::-1]  # txid (little-endian)
        result += struct.pack("<I", txin['vout'])  # vout

        if for_signing:
            if i == input_index:
                # Use script_code for the input being signed
                script_sig = bytes.fromhex(script_code)
                result += varint(len(script_sig)) + script_sig
            else:
                # Empty scriptSig
                result += varint(0)
        else:
            # Include scriptSig
            script_sig = bytes.fromhex(txin.get('scriptSig', ''))
            result += varint(len(script_sig)) + script_sig

        result += struct.pack("<I", 0xffffffff)  # sequence

    # Serialize outputs
    result += varint(len(tx['outputs']))  # Number of outputs
    for txout in tx['outputs']:
        result += struct.pack("<Q", txout['amount'])  # amount in satoshis
        script_pubkey = bytes.fromhex(create_script_pubkey(txout['address']))
        result += varint(len(script_pubkey)) + script_pubkey

    # Locktime
    result += struct.pack("<I", tx['locktime'])  # locktime

    return result

def sign_transaction(tx, privkey_hex):
    # Get the private key in bytes
    privkey_bytes = bytes.fromhex(privkey_hex)
    privkey = SigningKey.from_string(privkey_bytes, curve=SECP256k1)
    vk = privkey.get_verifying_key()
    public_key_bytes = vk.to_string("compressed")  # Compressed public key

    # Sign each input
    for index, txin in enumerate(tx['inputs']):
        # Get the scriptPubKey of the UTXO being spent
        script_pubkey = txin['scriptPubKey']
        # For P2PKH, the script code is the scriptPubKey
        script_code = script_pubkey
        # Create the serialization of the transaction for signing
        tx_serialized = serialize_transaction(tx, for_signing=True, input_index=index, script_code=script_code)
        # Append SIGHASH_ALL
        tx_serialized += struct.pack("<I", 1)  # SIGHASH_ALL

        # Compute the double SHA256 hash
        message_hash = hashlib.sha256(hashlib.sha256(tx_serialized).digest()).digest()

        # Sign the hash
        signature = privkey.sign_digest(message_hash, sigencode=util.sigencode_der_canonize)
        signature += b'\x01'  # Append SIGHASH_ALL

        # Build the scriptSig
        script_sig = (
            varint(len(signature)) + signature +
            varint(len(public_key_bytes)) + public_key_bytes
        )

        # Update the transaction input's scriptSig
        txin['scriptSig'] = script_sig.hex()

    return tx

def process_transaction(from_address, amount_doge):
    try:
        # Use the dumpprivkey RPC command to get the private key
        wif_private_key = rpc_connection.dumpprivkey(from_address)
        privkey_hex = wif_to_privkey_hex(wif_private_key)
    except JSONRPCException as e:
        print(f"Error getting private key: {e.error['message']}")
        return

    # Set up transaction details
    to_address = recipient_address  # Hardcoded recipient address
    amount_satoshis = int(amount_doge * 1e8)  # Convert DOGE to satoshis
    fee_satoshis = 2250000  # 1 DOGE fee (hardcoded)

    # Get UTXOs for the from_address
    utxos = get_utxos(from_address)

    # Create the raw transaction
    tx = create_raw_transaction(utxos, from_address, to_address, amount_satoshis, fee_satoshis)

    if tx:
        # Print transaction details
        print("\nTransaction Details:")
        print(f"From: {from_address}")
        print(f"To: {to_address}")
        print(f"Amount: {amount_doge} DOGE")
        print(f"Fee: {fee_satoshis / 1e8} DOGE")
        print(f"Total: {(amount_satoshis + fee_satoshis) / 1e8} DOGE")

        # Sign the transaction
        signed_tx = sign_transaction(tx, privkey_hex)
        
        if signed_tx:
            # Serialize the signed transaction
            raw_tx = serialize_transaction(signed_tx)
            raw_tx_hex = raw_tx.hex()
            
            print("\nSigned transaction (hex):")
            print(raw_tx_hex)
            
            try:
                txid = rpc_connection.sendrawtransaction(raw_tx_hex)
                print(f"\nTransaction broadcasted successfully!")
                print(f"TXID: {txid}")
                return txid
            except JSONRPCException as e:
                print(f"Error broadcasting transaction: {e.error['message']}")
        else:
            print("Failed to sign transaction.")
    else:
        print("Failed to create transaction.")

    return None

# Example usage
if __name__ == "__main__":
    from_address = "<sender_address>"
    amount_doge = 1.0

    process_transaction(from_address, amount_doge)