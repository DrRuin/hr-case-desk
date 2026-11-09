import { StrictMode } from "react"
import { createRoot } from "react-dom/client"
import { MotionConfig } from "motion/react"

import "./index.css"
import App from "./App.tsx"
import { TooltipProvider } from "@/components/ui/tooltip"

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <MotionConfig reducedMotion="user">
      <TooltipProvider delayDuration={200}>
        <App />
      </TooltipProvider>
    </MotionConfig>
  </StrictMode>
)
