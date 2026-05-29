FROM node:20-alpine AS frontend-build
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ ./
# Build the SPA to be served same-origin by the backend under /console:
#   VITE_BASE        -> asset paths + router basename live under /console/
#   VITE_BACKEND_URL -> empty => API calls are relative to the current origin
RUN VITE_BASE=/console/ VITE_BACKEND_URL= npm run build

FROM python:3.12-slim
WORKDIR /app

COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./backend/
COPY --from=frontend-build /app/frontend/dist ./frontend/dist

WORKDIR /app/backend
EXPOSE 8159
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8159"]
