FROM node:20.18.0-alpine

WORKDIR /app

# Instalar dependencias
COPY package.json ./
RUN npm install

# Copiar código fuente
COPY . .

EXPOSE 4321

ENV HOST=0.0.0.0
ENV PORT=4321

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "4321"]
