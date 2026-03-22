import { Navigate, Route, Routes } from "react-router-dom";
import CatalogPage from "./pages/CatalogPage";
import LoginPage from "./pages/LoginPage";
import SkillDetailPage from "./pages/SkillDetailPage";
import UserPage from "./pages/UserPage";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<CatalogPage />} />
      <Route path="/login" element={<LoginPage />} />
      <Route path="/skill/:name" element={<SkillDetailPage />} />
      <Route path="/user" element={<UserPage />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
