import { Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import HomePage from "./pages/HomePage";
import UploadPage from "./pages/UploadPage";
import EdaReviewPage from "./pages/EdaReviewPage";
import ModelSettingsPage from "./pages/ModelSettingsPage";
import ResultsPage from "./pages/ResultsPage";
import ValidationPage from "./pages/ValidationPage";
import CartRecommendationsPage from "./pages/CartRecommendationsPage";
import Layer1Refinement from "./pages/Layer1Refinement";

function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/upload" element={<UploadPage />} />
        <Route path="/layer1/:runId" element={<Layer1Refinement />} />
        <Route path="/eda/:runId" element={<EdaReviewPage />} />
        <Route path="/models/:runId" element={<ModelSettingsPage />} />
        <Route path="/results/:runId" element={<ResultsPage />} />
        <Route path="/validation/:runId" element={<ValidationPage />} />
        <Route path="/cart/:runId" element={<CartRecommendationsPage />} />
      </Routes>
    </Layout>
  );
}

export default App;
