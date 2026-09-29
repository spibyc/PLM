import "@fontsource/ibm-plex-sans/400.css";
import "@fontsource/ibm-plex-sans/500.css";
import "@fontsource/ibm-plex-sans/600.css";
import "@fontsource/ibm-plex-sans/700.css";
import "@fontsource/ibm-plex-mono/500.css";
import "@fontsource/ibm-plex-mono/600.css";
import "@mantine/core/styles.css";
import "@mantine/notifications/styles.css";
import "./styles.css";

import { MantineProvider } from "@mantine/core";
import { Notifications } from "@mantine/notifications";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import { Loading } from "./components/ui";
import { AuthProvider, useAuth } from "./lib/auth";
import { Audit, Users } from "./pages/Admin";
import Dashboard from "./pages/Dashboard";
import { LocationDetail, Labels } from "./pages/Locations";
import Locations from "./pages/Locations";
import Login from "./pages/Login";
import Lots, { LotDetail } from "./pages/Lots";
import { About, Account, NotFound, Scan, Search } from "./pages/Misc";
import PartDetail from "./pages/PartDetail";
import Parts from "./pages/Parts";
import { Receive, Transactions } from "./pages/Stores";
import { Suppliers, PurchaseOrders, Boms, Builds } from "./pages/Traceability";
import { theme } from "./theme";
import { branding } from "./branding";

const favicon = document.querySelector<HTMLLinkElement>('link[rel="icon"]');
if (favicon) { favicon.href = branding.logoPath; favicon.removeAttribute("type"); }
document.title = branding.productName;
import Documents from "./pages/Documents";
import PurchaseOrderDetail from "./pages/PurchaseOrderDetail";

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: (n, e: any) => n < 1 && !(e?.status >= 400 && e?.status < 500), refetchOnWindowFocus: false } },
});

function App() {
  const { me, loading } = useAuth();
  if (loading) return <Loading />;
  if (!me) return <Login />;
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/parts" element={<Parts />} />
        <Route path="/parts/:id" element={<PartDetail />} />
        <Route path="/lots" element={<Lots />} />
        <Route path="/lots/:id" element={<LotDetail />} />
        <Route path="/receive" element={<Receive />} />
        <Route path="/locations" element={<Locations />} />
        <Route path="/locations/:id" element={<LocationDetail />} />
        <Route path="/labels" element={<Labels />} />
        <Route path="/transactions" element={<Transactions />} />
        <Route path="/suppliers" element={<Suppliers />} />
        <Route path="/purchase-orders" element={<PurchaseOrders />} />
        <Route path="/purchase-orders/:id" element={<PurchaseOrderDetail />} />
        <Route path="/boms" element={<Boms />} />
        <Route path="/documents" element={<Documents />} />
        <Route path="/builds" element={<Builds />} />
        <Route path="/audit" element={<Audit />} />
        <Route path="/users" element={<Users />} />
        <Route path="/search" element={<Search />} />
        <Route path="/scan/:kind/:key" element={<Scan />} />
        <Route path="/about" element={<About />} />
        <Route path="/account" element={<Account />} />
        <Route path="*" element={<NotFound />} />
      </Routes>
    </Layout>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <MantineProvider theme={theme} defaultColorScheme="auto">
      <Notifications position="top-right" />
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <AuthProvider>
            <App />
          </AuthProvider>
        </BrowserRouter>
      </QueryClientProvider>
    </MantineProvider>
  </React.StrictMode>,
);
