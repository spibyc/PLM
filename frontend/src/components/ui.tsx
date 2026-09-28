import { Alert, Badge, Center, Group, Loader, Stack, Table, Text, Title } from "@mantine/core";
import { IconAlertTriangle } from "@tabler/icons-react";
import type { ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { STATUS_COLOR } from "../theme";

export function StatusBadge({ status }: { status?: string | null }) {
  if (!status) return null;
  const solid = status === "Released" || status === "Available" || status === "Quarantined" || status === "Prohibited";
  return (
    <Badge color={STATUS_COLOR[status] ?? "gray"} variant={solid ? "filled" : "light"} radius="sm" tt="none" fw={600}>
      {status}
    </Badge>
  );
}

export function Ident({ children, size }: { children: ReactNode; size?: "lg" }) {
  return <span className={size === "lg" ? "ident ident-lg" : "ident"}>{children}</span>;
}

export function PageHeader({ title, sub, actions }: { title: ReactNode; sub?: ReactNode; actions?: ReactNode }) {
  return (
    <Group justify="space-between" align="flex-end" mb="md" wrap="wrap">
      <Stack gap={2}>
        <Title order={2} fw={600}>{title}</Title>
        {sub && <Text c="dimmed" size="sm">{sub}</Text>}
      </Stack>
      {actions && <Group gap="xs">{actions}</Group>}
    </Group>
  );
}

export function Loading() {
  return <Center py="xl"><Loader size="sm" /></Center>;
}

export function ErrorBox({ error }: { error: unknown }) {
  if (!error) return null;
  return (
    <Alert color="red" icon={<IconAlertTriangle size={18} />} variant="light" mb="sm">
      {error instanceof Error ? error.message : String(error)}
    </Alert>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <Text c="dimmed" size="sm" py="md">{children}</Text>;
}

/** Table row that navigates on click and on Enter (keyboard accessible). */
export function LinkRow({ to, children }: { to: string; children: ReactNode }) {
  const nav = useNavigate();
  return (
    <Table.Tr data-href={to} tabIndex={0} onClick={() => nav(to)}
      onKeyDown={(e) => { if (e.key === "Enter") nav(to); }}>
      {children}
    </Table.Tr>
  );
}
