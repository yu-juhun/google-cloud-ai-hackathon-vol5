import { createRoot } from "react-dom/client";
import { AvatarPanel } from "./components/AvatarPanel";
import { PersonaSocket } from "./ws/PersonaSocket";

const WS_URL = import.meta.env.VITE_BACKEND_WS_URL ?? "ws://localhost:8080/ws/converse";

function App() {
  return <AvatarPanel socket={new PersonaSocket(WS_URL)} />;
}

createRoot(document.getElementById("root")!).render(<App />);
