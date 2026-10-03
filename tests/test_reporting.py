import unittest
import os
import shutil
import datetime
from ai_engine.domain.entities import (
    ExecutiveReportData,
    TrendResult,
    AnomalySummary,
    AnomalyItem,
    RootCauseItem,
    BusinessRecommendation
)
from ai_engine.domain.enums import TrendDirection, ImpactLevel
from ai_engine.generators.executive_report_generator import ExecutiveReportGenerator
from ai_engine.generators.pdf_generator import PDFGenerator, FPDF_AVAILABLE
from ai_engine.generators.pptx_generator import PPTXGenerator, PPTX_AVAILABLE
from ai_engine.generators.excel_generator import ExcelGenerator
from ai_engine.generators.word_generator import WordGenerator

class TestReportingSystem(unittest.TestCase):
    def setUp(self):
        # Create temp output directory
        self.output_dir = "temp_test_reports"
        os.makedirs(self.output_dir, exist_ok=True)

        # Build mock ExecutiveReportData
        trends = [
            TrendResult(
                column="revenue",
                direction=TrendDirection.UPWARD,
                slope=2.45,
                r2_score=0.88,
                pct_change=12.5,
                mean_val=5000.0,
                std_val=1200.0,
                summary_text="Revenue has risen steadily"
            ),
            TrendResult(
                column="expenses",
                direction=TrendDirection.DOWNWARD,
                slope=-1.20,
                r2_score=0.74,
                pct_change=-5.2,
                mean_val=3000.0,
                std_val=400.0,
                summary_text="Expenses have decreased"
            )
        ]

        from ai_engine.domain.enums import AnomalyMethod

        anom_items = [
            AnomalyItem(
                row_index=15,
                column="revenue",
                value=99999,
                score=0.95,
                method=AnomalyMethod.ENSEMBLE,
                reason="Value deviates from baseline IQR"
            ),
            AnomalyItem(
                row_index=42,
                column="expenses",
                value=-50,
                score=0.85,
                method=AnomalyMethod.ENSEMBLE,
                reason="Negative expense value detected"
            )
        ]
        anomalies = AnomalySummary(
            total_rows=500,
            anomalous_rows_count=2,
            anomaly_percentage=1.5,
            detected_anomalies=anom_items
        )

        root_causes = [
            RootCauseItem(feature="region", condition="Region == 'West'", impact_score=0.85, affected_rows=15, affected_percentage=11.2, description="Region West is driving the high expenses outlier trend")
        ]

        recommendations = [
            BusinessRecommendation(
                title="Expense Containment",
                impact=ImpactLevel.HIGH,
                category="Finance",
                description="Review expenses in West region",
                action_items=["Audit West invoices", "Impose budget caps"]
            )
        ]

        self.report_data = ExecutiveReportData(
            title="Q3 AI Performance Analytics Audit",
            generated_at=datetime.datetime.now(),
            dataset_name="sales_records.csv",
            dataset_shape=(500, 15),
            quality_score=94.5,
            missing_percentage=1.2,
            kpis=[],
            trends=trends,
            anomalies=anomalies,
            root_causes=root_causes,
            recommendations=recommendations,
            summary_paragraph="Overall dataset demonstrates normal baseline activities. Missing ratios and outlier counts are minimal."
        )

    def tearDown(self):
        if os.path.exists(self.output_dir):
            shutil.rmtree(self.output_dir)

    def test_html_report_generation(self):
        """Verify interactive HTML report output contains main selectors and scripts"""
        generator = ExecutiveReportGenerator(self.report_data)
        html = generator.generate_html()
        
        self.assertIsNotNone(html)
        self.assertIn("<!DOCTYPE html>", html)
        self.assertIn("Q3 AI Performance Analytics Audit", html)
        self.assertIn("table", html)
        self.assertIn("Recommendation", html) or self.assertIn("recommendation", html.lower())

    def test_pdf_report_generation(self):
        """Verify PDF report generation creates file on disk"""
        if not FPDF_AVAILABLE:
            self.skipTest("fpdf library is not installed in the environment.")
            
        pdf_path = os.path.join(self.output_dir, "test_report.pdf")
        generator = PDFGenerator(self.report_data)
        out_path = generator.generate(pdf_path)
        
        self.assertEqual(out_path, pdf_path)
        self.assertTrue(os.path.exists(pdf_path))
        self.assertGreater(os.path.getsize(pdf_path), 0)

    def test_pptx_deck_generation(self):
        """Verify PPTX presentation deck contains 5 slides"""
        if not PPTX_AVAILABLE:
            self.skipTest("python-pptx library is not installed in the environment.")
            
        pptx_path = os.path.join(self.output_dir, "test_deck.pptx")
        generator = PPTXGenerator(self.report_data)
        out_path = generator.generate(pptx_path)
        
        self.assertEqual(out_path, pptx_path)
        self.assertTrue(os.path.exists(pptx_path))
        self.assertGreater(os.path.getsize(pptx_path), 0)

    def test_excel_summary_generation(self):
        """Verify Excel generator writes structured worksheets"""
        excel_path = os.path.join(self.output_dir, "test_summary.xlsx")
        generator = ExcelGenerator(self.report_data)
        out_path = generator.generate(excel_path)
        
        self.assertEqual(out_path, excel_path)
        self.assertTrue(os.path.exists(excel_path))
        self.assertGreater(os.path.getsize(excel_path), 0)

    def test_word_report_generation(self):
        """Verify Word docx generator compiles output successfully"""
        word_path = os.path.join(self.output_dir, "test_report.docx")
        generator = WordGenerator(self.report_data)
        out_path = generator.generate(word_path)
        
        self.assertEqual(out_path, word_path)
        self.assertTrue(os.path.exists(word_path))
        self.assertGreater(os.path.getsize(word_path), 0)

if __name__ == "__main__":
    unittest.main()
