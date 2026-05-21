FROM node:20-alpine AS build
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install
COPY . .
ARG VITE_BACKEND_URL=/router-api
ARG VITE_FRONTEND_BASE=/router/
ARG VITE_FRONTEND_BASENAME=/router
ENV VITE_BACKEND_URL=${VITE_BACKEND_URL}
ENV VITE_FRONTEND_BASE=${VITE_FRONTEND_BASE}
ENV VITE_FRONTEND_BASENAME=${VITE_FRONTEND_BASENAME}
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
