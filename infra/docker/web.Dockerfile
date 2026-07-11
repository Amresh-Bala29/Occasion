# Build context is the repository root.
FROM node:24-alpine
WORKDIR /app
COPY apps/web/package.json ./
RUN npm install
COPY apps/web ./
RUN npm run build
EXPOSE 3000
CMD ["npm", "start"]
