FROM node:22-alpine AS build

WORKDIR /app
COPY package*.json ./
RUN npm install

COPY . .

ARG VITE_API_BASE_URL
ARG VITE_MAPBOX_ACCESS_TOKEN
ARG VITE_MAPBOX_STYLE_URL
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
ENV VITE_MAPBOX_ACCESS_TOKEN=$VITE_MAPBOX_ACCESS_TOKEN
ENV VITE_MAPBOX_STYLE_URL=$VITE_MAPBOX_STYLE_URL

RUN npm run build

FROM nginx:1.27-alpine

COPY nginx.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 8080
