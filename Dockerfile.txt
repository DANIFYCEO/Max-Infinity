FROM node:20-slim

WORKDIR /app

COPY baileys/package*.json ./
RUN npm install

COPY baileys/ ./

CMD ["node", "index.js"]
