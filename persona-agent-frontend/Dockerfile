# persona-agent-frontend/Dockerfile
FROM node:22-slim AS build
WORKDIR /app/persona-agent-frontend
COPY persona-agent-frontend/package.json ./
RUN npm install
COPY persona-agent-frontend/ .
ARG VITE_BACKEND_WS_URL="ws://localhost:8080/ws/converse"
ENV VITE_BACKEND_WS_URL=$VITE_BACKEND_WS_URL
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=build /app/persona-agent-frontend/dist /usr/share/nginx/html
COPY persona-agent-frontend/nginx.conf /etc/nginx/templates/default.conf.template
ENV PORT=8080
CMD ["nginx", "-g", "daemon off;"]
