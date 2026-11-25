#!/bin/sh
# Generate a self-signed test CA and one server certificate for the TLS
# variant (HTTPS on http-server:8443, MQTT over TLS on mosquitto-broker:8883).
#
#   sh scripts/gen_certs.sh [output_dir]      (default: ./certs)
#
# runner.py --tls calls this automatically (inside the netshoot image) when
# certs/ca.crt is missing. Test-only keys: never reuse them anywhere else.
set -e

OUT=${1:-certs}
mkdir -p "$OUT"
cd "$OUT"

DAYS=825
SAN="DNS:http-server,DNS:mosquitto-broker,DNS:localhost"

# Python 3.13 verifies strictly (VERIFY_X509_STRICT): the CA needs explicit
# basicConstraints and keyUsage, the server cert an authority key identifier.
openssl req -x509 -newkey rsa:2048 -nodes -sha256 -days "$DAYS" \
  -keyout ca.key -out ca.crt -subj "/CN=protocol-testbed-test-ca" \
  -addext "basicConstraints=critical,CA:TRUE" \
  -addext "keyUsage=critical,keyCertSign,cRLSign" \
  -addext "subjectKeyIdentifier=hash" 2>/dev/null

openssl req -newkey rsa:2048 -nodes -sha256 \
  -keyout server.key -out server.csr -subj "/CN=protocol-testbed-server" 2>/dev/null

printf 'subjectAltName=%s\nbasicConstraints=CA:FALSE\nkeyUsage=critical,digitalSignature,keyEncipherment\nextendedKeyUsage=serverAuth\nsubjectKeyIdentifier=hash\nauthorityKeyIdentifier=keyid\n' "$SAN" > server.ext

openssl x509 -req -in server.csr -CA ca.crt -CAkey ca.key -CAcreateserial \
  -out server.crt -days "$DAYS" -sha256 -extfile server.ext 2>/dev/null

rm -f server.csr server.ext ca.srl
# The broker runs as an unprivileged user and must be able to read the key.
chmod 644 server.key ca.key ca.crt server.crt

echo "[certs] wrote $(pwd)/ca.crt, server.crt, server.key (SAN: $SAN)"
openssl x509 -in server.crt -noout -subject -ext subjectAltName
