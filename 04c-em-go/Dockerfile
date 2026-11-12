# Compila o Ingressa num binário só, sem dependências...
FROM golang:1.26-alpine AS compilacao
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY *.go ./
RUN CGO_ENABLED=0 go build -o /ingressa .

# ...e roda numa imagem mínima. Um processo Go usa todas as CPUs que o
# container tiver (desde o Go 1.25, ele respeita o limite de CPU do Docker).
FROM alpine:3.22
COPY --from=compilacao /ingressa /ingressa
EXPOSE 8000
HEALTHCHECK --interval=2s --timeout=2s --retries=30 \
  CMD wget -qO- http://localhost:8000/health || exit 1
CMD ["/ingressa"]
