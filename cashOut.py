#!/usr/bin/env python3

"""
cashOut.py

This script signs and sends a Dogecoin transaction from a specified address using the private key directly,
without importing the address into the Dogecoin Core wallet.
"""

from decimal import Decimal
from bitcoinrpc.authproxy import AuthServiceProxy, JSONRPCException
from ecdsa import SigningKey, SECP256k1, util
import hashlib
import struct
import base58
import configparser

# Load RPC configuration from RPC.conf
config = configparser.ConfigParser()
config.read('RPC.conf')

rpc_user = config['rpcconfig']['rpcuser']
rpc_password = config['rpcconfig']['rpcpassword']
rpc_host = config['rpcconfig']['rpchost']
rpc_port = int(config['rpcconfig']['rpcport'])

# Wallet information
from_address = "<pool_address>"
privkey_hex = "<pool_private_key>"

# Dev fee information
dev_fee_1_address = "<first_dev_fee_address>"
dev_fee_2_address = "<second_dev_fee_address>"
dev_fee_3_address = "<third_dev_fee_address>"

dev_fee_1_percent = 0.01  # 1%
dev_fee_2_percent = 0.00  # 0.5%
dev_fee_3_percent = 0.00  # 0.3%

# At the top of the file, with other global variables
global win_differential
win_differential = 0

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
    rpc_connection = AuthServiceProxy(f"http://{rpc_user}:{rpc_password}@{rpc_host}:{rpc_port}")
    utxos = []

    try:
        # Get the list of unspent transaction outputs for the address
        utxos_list = rpc_connection.listunspent(1, 9999999, [address])
        for utxo in utxos_list:
            utxo_info = {
                'transaction_hash': utxo['txid'],
                'index': utxo['vout'],
                'value': int(Decimal(str(utxo['amount'])) * Decimal('1e8')),  # Convert DOGE to satoshis
                'scriptPubKey': utxo['scriptPubKey'],
            }
            utxos.append(utxo_info)
            print(f"UTXO: {utxo_info}")  # Print UTXO details
    except JSONRPCException as e:
        print(f"An error occurred while retrieving UTXOs: {e.error['message']}")

    return utxos

def create_script_pubkey(address):
    # Decode the address (assuming it's a base58check encoded address)
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

def create_raw_transaction(utxos, to_address, amount_satoshis, fee_satoshis, win_differential_satoshis):
    inputs = []
    outputs = []
    total_input = 0

    # Calculate dev fees based on win_differential
    dev_fees = [
        (dev_fee_1_address, int(win_differential_satoshis * dev_fee_1_percent)),
        (dev_fee_2_address, int(win_differential_satoshis * dev_fee_2_percent)),
        (dev_fee_3_address, int(win_differential_satoshis * dev_fee_3_percent))
    ]
    
    # Filter out dev fees that are 0
    dev_fees = [(address, amount) for address, amount in dev_fees if amount > 0]
    
    # Total amount needed (send amount + dev fees + transaction fee)
    total_needed = amount_satoshis + sum(amount for _, amount in dev_fees) + fee_satoshis

    print(f"Total needed: {total_needed} satoshis")
    print(f"Available UTXOs: {utxos}")
    
    # Select UTXOs to cover the total amount needed
    for utxo in utxos:
        inputs.append({
            'txid': utxo['transaction_hash'],
            'vout': utxo['index'],
            'scriptPubKey': utxo['scriptPubKey'],  # Needed for signing
            'amount': utxo['value'],  # in satoshis
        })
        total_input += utxo['value']
        print(f"Running total: {total_input} satoshis")
        if total_input >= total_needed:
            break

    if total_input < total_needed:
        print(f"Insufficient funds. Total input: {total_input}, Total needed: {total_needed}")
        raise Exception("Insufficient funds")

    # Outputs
    # Recipient output (full amount)
    outputs.append({
        'address': to_address,
        'amount': amount_satoshis,
    })

    # Dev fee outputs (only for non-zero fees)
    for address, amount in dev_fees:
        outputs.append({
            'address': address,
            'amount': amount,
        })

    # Change output (if any)
    change_satoshis = total_input - total_needed
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

def broadcast_transaction(raw_tx_hex):
    """
    Broadcast the transaction to the network via Dogecoin Core RPC.
    """
    rpc_connection = AuthServiceProxy(f"http://{rpc_user}:{rpc_password}@{rpc_host}:{rpc_port}")

    try:
        txid = rpc_connection.sendrawtransaction(raw_tx_hex)
        print(f"Transaction broadcasted successfully. TXID: {txid}")
        return txid
    except JSONRPCException as e:
        print(f"An error occurred: {e.error['message']}")
        return None

def send_doge(to_address, amount_doge, win_differential):
    amount_satoshis = int(amount_doge * 1e8)
    win_differential_satoshis = int(win_differential * 1e8)
    fee_doge = 0.0225  # Define the transaction fee in DOGE (adjust as needed)
    fee_satoshis = int(fee_doge * 1e8)  # Convert fee to satoshis

    utxos = get_utxos(from_address)

    # Create the raw transaction
    tx = create_raw_transaction(utxos, to_address, amount_satoshis, fee_satoshis, win_differential_satoshis)

    # Sign the transaction
    tx_signed = sign_transaction(tx, privkey_hex)

    # Serialize the signed transaction
    raw_tx = serialize_transaction(tx_signed)
    raw_tx_hex = raw_tx.hex()

    # Print the raw transaction hex
    print(f"Raw transaction hex: {raw_tx_hex}")

    # Print win differential
    print(f"Win Differential: {win_differential} DOGE")

    # Broadcast the transaction
    txid = broadcast_transaction(raw_tx_hex)
    
    if txid:
        print(f"Transaction successful. TXID: {txid}")
        print(f"Amount sent: {amount_doge} DOGE")
        print(f"Win Differential: {win_differential} DOGE")
    else:
        print("Transaction failed.")

    return txid

def public_key_to_address(public_key_bytes):
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

# Verify the derived address matches the expected address
if __name__ == "__main__":
    # Use the public key from the private key
    privkey_bytes = bytes.fromhex(privkey_hex)
    privkey = SigningKey.from_string(privkey_bytes, curve=SECP256k1)
    vk = privkey.get_verifying_key()
    public_key_bytes = vk.to_string("compressed")  # Compressed public key

    # Generate the address from the public key
    derived_address = public_key_to_address(public_key_bytes)
    print(f"Derived Address: {derived_address}")

    # Compare with the expected address
    expected_address = from_address
    if derived_address == expected_address:
        print("The addresses match.")
    else:
        print("The addresses do not match. Please check the public key.")

    # Example usage
    recipient_address = "<recipient_address>"
    amount_to_send = 1  # Amount in DOGE
    send_doge(recipient_address, amount_to_send, win_differential)