import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { Toaster } from "sonner";
import { TooltipProvider } from "@/components/ui/tooltip";

import "./styles.css";
import { ChannelPage, ChannelsPage, ClaimsPage, DashboardPage, EntitiesPage, EntityPage, PostPage, Shell, SystemPage } from "./App";

const client = new QueryClient();
createRoot(document.getElementById("root")!).render(<StrictMode><QueryClientProvider client={client}><TooltipProvider><BrowserRouter><Routes><Route element={<Shell />}><Route path="/" element={<DashboardPage />} /><Route path="/entities" element={<EntitiesPage />} /><Route path="/entities/:id" element={<EntityPage />} /><Route path="/channels" element={<ChannelsPage />} /><Route path="/channels/:id" element={<ChannelPage />} /><Route path="/claims" element={<ClaimsPage />} /><Route path="/system" element={<SystemPage />} /><Route path="/posts/:id" element={<PostPage />} /></Route></Routes><Toaster richColors position="bottom-right" /></BrowserRouter></TooltipProvider></QueryClientProvider></StrictMode>);
