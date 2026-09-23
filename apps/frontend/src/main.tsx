import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { Toaster } from "sonner";

import "./styles.css";
import { ChannelsPage, DashboardPage, EntitiesPage, EntityPage, PostPage, Shell } from "./App";

const client = new QueryClient();
createRoot(document.getElementById("root")!).render(<StrictMode><QueryClientProvider client={client}><BrowserRouter><Routes><Route element={<Shell />}><Route path="/" element={<DashboardPage />} /><Route path="/entities" element={<EntitiesPage />} /><Route path="/entities/:id" element={<EntityPage />} /><Route path="/channels" element={<ChannelsPage />} /><Route path="/posts/:id" element={<PostPage />} /></Route></Routes><Toaster richColors position="bottom-right" /></BrowserRouter></QueryClientProvider></StrictMode>);
