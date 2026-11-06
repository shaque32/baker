// Makes the license server's Ed25519 signing key. Run once, on your own computer:
//   node workers/license/make-key.mjs k1
// It prints two things and saves nothing:
// 1. the private key (JWK) to paste into the Worker as the secret SIGNING_KEY_JWK
//    (npx wrangler secret put SIGNING_KEY_JWK). Never commit it or paste it anywhere else.
// 2. the line for account/license.py's SIGNING_KEYS: the public half, which is safe to commit.
const kid = process.argv[2] || "k1";
if (!/^[A-Za-z0-9_-]{1,40}$/.test(kid)) throw new Error("the key id is letters, digits, - and _");
const keys = await crypto.subtle.generateKey({ name: "Ed25519" }, true, ["sign", "verify"]);
const jwk = await crypto.subtle.exportKey("jwk", keys.privateKey);
const pub = Buffer.from(await crypto.subtle.exportKey("raw", keys.publicKey)).toString("hex");
console.log("1. SIGNING_KEY_JWK (secret; paste into `npx wrangler secret put SIGNING_KEY_JWK`):\n");
console.log(JSON.stringify({ kty: jwk.kty, crv: jwk.crv, d: jwk.d, x: jwk.x }));
console.log(`\n2. KEY_ID = "${kid}" in wrangler.toml, and in account/license.py:\n`);
console.log(`SIGNING_KEYS: dict[str, str] = {"${kid}": "${pub}"}`);
