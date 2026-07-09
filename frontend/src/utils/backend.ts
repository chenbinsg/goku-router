export const getBackendBaseUrl = () => {
  const configured = import.meta.env.VITE_BACKEND_URL;
  if (configured !== undefined && configured !== '') {
    return configured;
  }
  if (configured === '') {
    return '';
  }
  return `http://localhost:${import.meta.env.VITE_BACKEND_PORT || '8159'}`;
};
