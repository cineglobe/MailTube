import { HistoryScreen } from "@/components/history-screen"
import { ProtectedShell } from "@/components/protected-shell"

export default function HistoryPage() {
  return (
    <ProtectedShell>
      <HistoryScreen />
    </ProtectedShell>
  )
}
