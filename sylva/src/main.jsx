import React from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App.jsx";
import "./tokens.css";
import "./styles.css";
import "./acid.css";
import "./fresh.css";

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
