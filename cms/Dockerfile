FROM node:20.18.0-alpine

# Dependencias nativas necesarias para módulos de Node en Alpine
RUN apk update && apk add --no-cache build-base gcc autoconf automake zlib-dev libpng-dev vips-dev git

WORKDIR /srv/app

COPY package.json ./
RUN npm install

COPY . .

EXPOSE 1337

ENV NODE_ENV=development

CMD ["npm", "run", "develop"]
