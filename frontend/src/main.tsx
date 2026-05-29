import React from 'react';
import ReactDOM from 'react-dom';
import { BrowserRouter } from 'react-router-dom';
import App from './App';
import { I18nProvider } from './i18n';

ReactDOM.render(
  <React.StrictMode>
    <I18nProvider>
      <BrowserRouter basename={import.meta.env.BASE_URL.replace(/\/+$/, '') || undefined}>
        <App />
      </BrowserRouter>
    </I18nProvider>
  </React.StrictMode>,
  document.getElementById('root')
);
