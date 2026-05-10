#!/bin/sh
set -e
CERTS=/certs

mkdir -p "$CERTS"

if [ -f "$CERTS/ca.crt" ]; then
  echo "Certs already exist, skipping generation."
  exit 0
fi

echo "==> Generating CA"
openssl genrsa -out "$CERTS/ca.key" 4096
openssl req -new -x509 -days 3650 -key "$CERTS/ca.key" -out "$CERTS/ca.crt" \
  -subj "/CN=fpga-internal-ca/O=FPGA Cluster/C=RU"

sign_cert() {
  NAME=$1
  shift
  SANS=$@

  openssl genrsa -out "$CERTS/$NAME.key" 2048

  cat > /tmp/$NAME.cnf <<EOF
[req]
req_extensions = v3_req
distinguished_name = dn
[dn]
[v3_req]
subjectAltName = $SANS
EOF

  openssl req -new -key "$CERTS/$NAME.key" -out /tmp/$NAME.csr \
    -subj "/CN=$NAME/O=FPGA Cluster/C=RU" \
    -config /tmp/$NAME.cnf

  openssl x509 -req -days 825 \
    -in /tmp/$NAME.csr \
    -CA "$CERTS/ca.crt" -CAkey "$CERTS/ca.key" -CAcreateserial \
    -out "$CERTS/$NAME.crt" \
    -extensions v3_req -extfile /tmp/$NAME.cnf
  echo "  signed $NAME"
}

MASTERS="DNS:fpga-master-1,DNS:fpga-master-2,DNS:fpga-master-3,IP:172.20.0.31,IP:172.20.0.32,IP:172.20.0.33,IP:127.0.0.1"
WORKERS="DNS:fpga-worker-1,DNS:fpga-worker-2,IP:172.20.0.41,IP:172.20.0.42,IP:127.0.0.1"
EMULATORS="DNS:emulator-1,DNS:emulator-2,DNS:emulator-3,IP:172.20.0.21,IP:172.20.0.22,IP:172.20.0.23,IP:127.0.0.1"
NGINX="DNS:fpga-dashboard,DNS:localhost,IP:172.20.0.60,IP:127.0.0.1"
CICD="DNS:fpga-cicd,IP:172.20.0.70,IP:127.0.0.1"
ETCD="DNS:etcd,IP:172.20.0.11,IP:127.0.0.1"

sign_cert master   "$MASTERS"
sign_cert worker   "$WORKERS"
sign_cert emulator "$EMULATORS"
sign_cert nginx    "$NGINX"
sign_cert cicd     "$CICD"
sign_cert etcd     "$ETCD"

chmod 644 "$CERTS"/*.crt "$CERTS"/*.key 2>/dev/null || true
echo "==> All certificates generated in $CERTS"
