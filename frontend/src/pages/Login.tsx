import { ActionIcon, Button, Group, Paper, PasswordInput, Stack, Text, TextInput, Title, useMantineColorScheme, useComputedColorScheme } from "@mantine/core";
import { IconMoon, IconSun } from "@tabler/icons-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { branding, subtitle } from "../branding";
import { ErrorBox } from "../components/ui";
import { useAuth } from "../lib/auth";

export default function Login() {
  const { login } = useAuth();
  const { toggleColorScheme } = useMantineColorScheme();
  const colorScheme = useComputedColorScheme("light");
  const [u, setU] = useState("");
  const [p, setP] = useState("");
  const [err, setErr] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  return (
    <div style={{ minHeight: "100vh", display: "grid", placeItems: "center", padding: 16 }}>
      <div style={{ position: "fixed", top: 16, right: 16 }}>
        <ActionIcon
          variant="default"
          size="lg"
          onClick={toggleColorScheme}
          aria-label="Toggle colour scheme"
          title={colorScheme === "dark" ? "Use light mode" : "Use dark mode"}
        >
          {colorScheme === "dark" ? <IconSun size={18} /> : <IconMoon size={18} />}
        </ActionIcon>
      </div>

      <Paper withBorder p="xl" w={380} maw="100%" radius="sm">
        <form onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          setErr(null);
          try {
            await login(u, p);
          } catch (x) {
            setErr(x);
          } finally {
            setBusy(false);
          }
        }}>
          <Stack>
            <Group gap="md" wrap="nowrap">
              <img
                src={branding.logoPath}
                alt={branding.logoAlt}
                style={{ width: 52, height: 52, objectFit: "contain" }}
              />
              <div>
                <Title order={3}>{branding.productName}</Title>
                <Text size="sm" c="dimmed">{subtitle}</Text>
              </div>
            </Group>

            <TextInput
              label="Username"
              value={u}
              onChange={(e) => setU(e.currentTarget.value)}
              autoComplete="username"
              autoFocus
              required
            />

            <PasswordInput
              label="Password"
              value={p}
              onChange={(e) => setP(e.currentTarget.value)}
              autoComplete="current-password"
              required
            />

            <ErrorBox error={err} />

            <Button type="submit" loading={busy}>Sign in</Button>
            <Button component={Link} to="/" variant="subtle">Continue as public viewer</Button>

            <Text size="xs" c="dimmed">
              All activity is recorded in the audit trail.
            </Text>
          </Stack>
        </form>
      </Paper>
    </div>
  );
}
