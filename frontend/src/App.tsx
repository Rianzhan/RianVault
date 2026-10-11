import { Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import ConversationViewer from "./pages/ConversationViewer";
import ExportPage from "./pages/ExportPage";
import Home from "./pages/Home";
import ImportPage from "./pages/ImportPage";
import MemoryDetail from "./pages/MemoryDetail";
import MemoryLibrary from "./pages/MemoryLibrary";
import MigrationAudit from "./pages/MigrationAudit";
import Search from "./pages/Search";
import Settings from "./pages/Settings";

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/search" element={<Search />} />
        <Route path="/conversations" element={<ConversationViewer />} />
        <Route path="/conversations/:id" element={<ConversationViewer />} />
        <Route path="/memories" element={<MemoryLibrary />} />
        <Route path="/memories/:id" element={<MemoryDetail />} />
        <Route path="/migration-audit" element={<MigrationAudit />} />
        <Route path="/import" element={<ImportPage />} />
        <Route path="/export" element={<ExportPage />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="*" element={<Home />} />
      </Routes>
    </Layout>
  );
}
