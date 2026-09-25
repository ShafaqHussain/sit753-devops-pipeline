import sodium from "libsodium-wrappers";

const readyPromise = sodium.ready;
const PRIVATE_KEY_PREFIX = "e2e_private_key_";

async function initSodium() {
  await readyPromise;
  return sodium;
}

function toB64(bytes) {
  return sodium.to_base64(bytes, sodium.base64_variants.ORIGINAL);
}

function fromB64(str) {
  return sodium.from_base64(str, sodium.base64_variants.ORIGINAL);
}

export async function generateKeyPair() {
  await initSodium();
  const { publicKey, privateKey } = sodium.crypto_box_keypair();
  return { publicKey: toB64(publicKey), privateKey: toB64(privateKey) };
}

export function savePrivateKey(userId, privateKeyB64) {
  localStorage.setItem(PRIVATE_KEY_PREFIX + userId, privateKeyB64);
}

export function loadPrivateKey(userId) {
  return localStorage.getItem(PRIVATE_KEY_PREFIX + userId);
}

/**
 * Encrypts `plaintext` once per recipient with libsodium's crypto_box
 * (X25519 + XSalsa20-Poly1305), so the server only ever stores/relays
 * ciphertext. The same nonce is safe to reuse across recipients here
 * because crypto_box derives a distinct shared key per (sender, recipient)
 * keypair — the (nonce, shared-key) pair is what must stay unique.
 */
export async function encryptForRecipients(plaintext, recipients, myPrivateKeyB64) {
  await initSodium();

  const nonce = sodium.randombytes_buf(sodium.crypto_box_NONCEBYTES);
  const myPrivateKey = fromB64(myPrivateKeyB64);
  const messageBytes = sodium.from_string(plaintext);

  const ciphertexts = {};
  for (const user of recipients) {
    if (!user.public_key) continue;
    const recipientPublicKey = fromB64(user.public_key);
    const cipher = sodium.crypto_box_easy(messageBytes, nonce, recipientPublicKey, myPrivateKey);
    ciphertexts[user.id] = toB64(cipher);
  }

  return { nonce: toB64(nonce), ciphertexts };
}

/** Returns the decrypted plaintext, or null if decryption fails (wrong/missing key, corrupted data). */
export async function decryptMessage({ ciphertext, nonce, senderPublicKeyB64, myPrivateKeyB64 }) {
  await initSodium();
  try {
    const plainBytes = sodium.crypto_box_open_easy(
      fromB64(ciphertext),
      fromB64(nonce),
      fromB64(senderPublicKeyB64),
      fromB64(myPrivateKeyB64)
    );
    return sodium.to_string(plainBytes);
  } catch {
    return null;
  }
}
