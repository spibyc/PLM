import { Button, Paper, PasswordInput, Stack, Text, TextInput, Title } from "@mantine/core";
import { useState } from "react";
import { ErrorBox } from "../components/ui";
import { useAuth } from "../lib/auth";

export default function Login() {
  const { login } = useAuth();
  const [u, setU] = useState("");
  const [p, setP] = useState("");
  const [err, setErr] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  return (
    <div style={{ minHeight: "100vh", display: "grid", placeItems: "center", padding: 16 }}>
      <Paper withBorder p="xl" w={380} radius="sm">
        <form onSubmit={async (e) => {
          e.preventDefault(); setBusy(true); setErr(null);
          try { await login(u, p); } catch (x) { setErr(x); } finally { setBusy(false); }
        }}>
          <Stack>
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <img src="/favicon.svg" width={34} height={34} alt="" />
              <div>
                <Title order={3}>PLM</Title>
                <Text size="sm" c="dimmed">Parts, stock and traceability</Text>
              </div>
            </div>
            <TextInput label="Username" value={u} onChange={(e) => setU(e.currentTarget.value)} autoComplete="username" autoFocus required />
            <PasswordInput label="Password" value={p} onChange={(e) => setP(e.currentTarget.value)} autoComplete="current-password" required />
            <ErrorBox error={err} />
            <Button type="submit" loading={busy}>Sign in</Button>
            <Text size="xs" c="dimmed">All activity is recorded in the audit trail.</Text>
          </Stack>
        </form>
      </Paper>
    </div>
  );
}
