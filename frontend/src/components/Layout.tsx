import { AppShell, Badge, Burger, Group, Menu, NavLink, ScrollArea, Text, TextInput, UnstyledButton } from "@mantine/core";
import { useDisclosure } from "@mantine/hooks";
import {
  IconArrowsExchange, IconBox, IconBuildingFactory2, IconChevronDown, IconCpu,
  IconFileDescription, IconGitPullRequest, IconHistory, IconInfoCircle, IconLayoutDashboard, IconListTree,
  IconMapPin, IconPackageImport, IconSearch, IconShoppingCart, IconTruckDelivery, IconUsers,
} from "@tabler/icons-react";
import { useState, type ReactNode } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../lib/auth";
import { branding, subtitle } from "../branding";

type Item = { label: string; to?: string; icon: ReactNode; perm?: string; planned?: boolean };
const SECTIONS: { title: string; items: Item[] }[] = [
  { title: "Overview", items: [{ label: "Dashboard", to: "/", icon: <IconLayoutDashboard size={18} /> }] },
  { title: "Engineering", items: [
    { label: "Parts", to: "/parts", icon: <IconCpu size={18} />, perm: "item:read" },
    { label: "BOMs", to: "/boms", icon: <IconListTree size={18} />, perm: "bom:read" },
    { label: "Changes (ECR/ECO)", icon: <IconGitPullRequest size={18} />, planned: true },
    { label: "Documents", to: "/documents", icon: <IconFileDescription size={18} />, perm: "document:read" },
  ] },
  { title: "Stores", items: [
    { label: "Lots", to: "/lots", icon: <IconBox size={18} />, perm: "inventory:read" },
    { label: "Receive stock", to: "/receive", icon: <IconPackageImport size={18} />, perm: "inventory:receive" },
    { label: "Locations", to: "/locations", icon: <IconMapPin size={18} />, perm: "location:read" },
    { label: "Transactions", to: "/transactions", icon: <IconArrowsExchange size={18} />, perm: "inventory:read" },
  ] },
  { title: "Purchasing", items: [
    { label: "Suppliers", to: "/suppliers", icon: <IconTruckDelivery size={18} />, perm: "supplier:read" },
    { label: "Purchase orders", to: "/purchase-orders", icon: <IconShoppingCart size={18} />, perm: "po:read" },
  ] },
  { title: "Production", items: [
    { label: "Builds & serials", to: "/builds", icon: <IconBuildingFactory2 size={18} />, perm: "build:read" },
  ] },
  { title: "Quality & admin", items: [
    { label: "Audit trail", to: "/audit", icon: <IconHistory size={18} />, perm: "audit:read" },
    { label: "Users & roles", to: "/users", icon: <IconUsers size={18} />, perm: "users:admin" },
    { label: "About this system", to: "/about", icon: <IconInfoCircle size={18} /> },
  ] },
];

export function Layout({ children }: { children: ReactNode }) {
  const [opened, { toggle, close }] = useDisclosure();
  const { me, logout, can } = useAuth();
  const loc = useLocation();
  const nav = useNavigate();
  const [q, setQ] = useState("");

  const active = (to: string) => (to === "/" ? loc.pathname === "/" : loc.pathname.startsWith(to));

  return (
    <AppShell header={{ height: 56 }} navbar={{ width: 236, breakpoint: "sm", collapsed: { mobile: !opened } }}
      padding="lg" styles={{ main: { background: "var(--plm-paper)" } }}>
      <AppShell.Header className="no-print" style={{ borderBottom: "1px solid var(--plm-rule)" }}>
        <Group h="100%" px="md" justify="space-between" wrap="nowrap">
          <Group gap="sm" wrap="nowrap">
            <Burger opened={opened} onClick={toggle} hiddenFrom="sm" size="sm" aria-label="Toggle navigation" />
            <Link to="/" style={{ display: "flex", alignItems: "center", gap: 8, textDecoration: "none", color: "inherit" }}>
              <img src={branding.logoPath} width={30} height={30} alt={branding.logoAlt} style={{ objectFit: "contain" }} />
              <div><Text fw={700} size="lg" lh={1}>{branding.productName}</Text><Text size="xs" c="dimmed" lh={1.2}>{subtitle}</Text></div>
            </Link>
          </Group>
          <form style={{ flex: 1, maxWidth: 520 }} onSubmit={(e) => { e.preventDefault(); if (q.trim().length >= 2) nav(`/search?q=${encodeURIComponent(q.trim())}`); }}>
            <TextInput leftSection={<IconSearch size={16} />} placeholder="Part number, MPN, lot, location… or scan a label"
              value={q} onChange={(e) => setQ(e.currentTarget.value)} aria-label="Search" />
          </form>
          <Menu position="bottom-end" width={240}>
            <Menu.Target>
              <UnstyledButton aria-label="Account menu">
                <Group gap={6} wrap="nowrap">
                  <Text size="sm" fw={500} visibleFrom="sm">{me?.full_name}</Text>
                  <IconChevronDown size={14} />
                </Group>
              </UnstyledButton>
            </Menu.Target>
            <Menu.Dropdown>
              <Menu.Label>Signed in as {me?.username}</Menu.Label>
              <Menu.Item disabled>Roles: {me?.roles.join(", ") || "none"}</Menu.Item>
              <Menu.Item component={Link} to="/account">Change password</Menu.Item>
              <Menu.Divider />
              <Menu.Item color="red" onClick={() => logout()}>Sign out</Menu.Item>
            </Menu.Dropdown>
          </Menu>
        </Group>
      </AppShell.Header>
      <AppShell.Navbar className="no-print" p="xs" style={{ borderRight: "1px solid var(--plm-rule)" }}>
        <ScrollArea>
          {SECTIONS.map((s) => {
            const items = s.items.filter((i) => i.planned || !i.perm || can(i.perm));
            if (!items.length) return null;
            return (
              <div key={s.title} style={{ marginBottom: 10 }}>
                <Text size="xs" c="dimmed" fw={600} px="sm" py={4}>{s.title}</Text>
                {items.map((i) =>
                  i.planned ? (
                    <NavLink key={i.label} label={i.label} leftSection={i.icon} disabled
                      rightSection={<Badge size="xs" variant="outline" color="gray" tt="none">Planned</Badge>} />
                  ) : (
                    <NavLink key={i.label} label={i.label} leftSection={i.icon} component={Link} to={i.to!}
                      active={active(i.to!)} onClick={close} />
                  ),
                )}
              </div>
            );
          })}
        </ScrollArea>
      </AppShell.Navbar>
      <AppShell.Main>{children}</AppShell.Main>
    </AppShell>
  );
}
