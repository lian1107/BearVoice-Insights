import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./app/App";

const root = document.getElementById("root");
if (!root) {
  throw new Error("找不到前端挂载节点 #root");
}

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
