FROM alpine:3.19
RUN apk add --no-cache openssl
COPY gen-certs.sh /gen-certs.sh
RUN chmod +x /gen-certs.sh
CMD ["/gen-certs.sh"]
