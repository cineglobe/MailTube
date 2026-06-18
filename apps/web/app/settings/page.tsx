import { ProtectedShell } from "@/components/protected-shell"
import { SettingsScreen } from "@/components/settings-screen"

export default function SettingsPage() {
  return (
    <ProtectedShell>
      <SettingsScreen />
    </ProtectedShell>
  )
}
