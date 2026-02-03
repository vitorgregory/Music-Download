Place TLS certificates at `docker/nginx/certs/fullchain.pem` and `docker/nginx/certs/privkey.pem`.

Example using certbot (host):

sudo certbot certonly --standalone -d your.domain.tld
sudo mkdir -p docker/nginx/certs
sudo cp /etc/letsencrypt/live/your.domain.tld/fullchain.pem docker/nginx/certs/
sudo cp /etc/letsencrypt/live/your.domain.tld/privkey.pem docker/nginx/certs/

Then run:

docker-compose up -d nginx
