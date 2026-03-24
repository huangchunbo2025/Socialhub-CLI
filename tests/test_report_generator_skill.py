"""Tests for the report-generator skill v3.0 (Consulting-Grade Reports)."""

import os
import tempfile
from pathlib import Path

import pytest

import sys
skill_path = Path(__file__).parent.parent / "cli" / "skills" / "store" / "report-generator"
sys.path.insert(0, str(skill_path))

from main import (
    generate_consulting_report,
    generate_pestel_report,
    generate_porter_report,
    generate_swot_report,
    generate_valuechain_report,
    generate_action_report,
    generate_demo_report,
    _validate_output_path,
    _detect_context,
    _executive_insight,
    _generate_pestel,
    _generate_porter,
    _generate_swot,
    _generate_valuechain,
    _generate_5w2h,
    _generate_bcg_matrix,
    INDICATORS,
)


class TestInputValidation:
    """Test input validation and security checks."""

    def test_path_traversal_blocked(self):
        """Test that path traversal attacks are blocked."""
        with pytest.raises(ValueError, match="disallowed pattern"):
            _validate_output_path("../../../etc/passwd.md")

    def test_invalid_extension_blocked(self):
        """Test that invalid file extensions are blocked."""
        with pytest.raises(ValueError, match="Invalid file type"):
            _validate_output_path("output.exe")

    def test_valid_md_extension(self):
        """Test that .md extension is allowed."""
        path = _validate_output_path("report.md")
        assert path.suffix == ".md"


class TestContextDetection:
    """Test automatic context detection."""

    def test_detect_external_context(self):
        """Test detection of external environment context."""
        assert _detect_context("市场宏观环境分析") == "external"
        assert _detect_context("Market trends analysis") == "external"
        assert _detect_context("政策环境研究") == "external"

    def test_detect_competitive_context(self):
        """Test detection of competitive analysis context."""
        assert _detect_context("竞争对手分析") == "competitive"
        assert _detect_context("Tesla vs BYD comparison") == "competitive"
        assert _detect_context("优势劣势对比") == "competitive"

    def test_detect_process_context(self):
        """Test detection of process/workflow context."""
        assert _detect_context("业务流程优化") == "process"
        assert _detect_context("How to implement") == "process"
        assert _detect_context("步骤方法论") == "process"

    def test_detect_action_context(self):
        """Test detection of action plan context."""
        assert _detect_context("执行方案制定") == "action"
        assert _detect_context("Implementation plan") == "action"
        assert _detect_context("行动计划") == "action"

    def test_detect_comprehensive_context(self):
        """Test fallback to comprehensive context."""
        assert _detect_context("General business topic") == "comprehensive"
        assert _detect_context("随机主题") == "comprehensive"


class TestExecutiveInsight:
    """Test Executive Insight formatting."""

    def test_insight_format(self):
        """Test that insights are properly formatted."""
        insight = _executive_insight("This is a key insight")
        assert "**Executive Insight:**" in insight
        assert "This is a key insight" in insight
        assert ">" in insight  # Blockquote format


class TestIndicators:
    """Test visual indicators."""

    def test_indicators_exist(self):
        """Test that all required indicators exist."""
        assert "strength" in INDICATORS
        assert "weakness" in INDICATORS
        assert "opportunity" in INDICATORS
        assert "threat" in INDICATORS
        assert "high" in INDICATORS
        assert "medium" in INDICATORS
        assert "low" in INDICATORS

    def test_indicator_symbols(self):
        """Test indicator symbols are non-empty."""
        for key, value in INDICATORS.items():
            assert len(value) > 0


class TestPESTELFramework:
    """Test PESTEL analysis generation."""

    def test_pestel_contains_all_dimensions(self):
        """Test that PESTEL contains all six dimensions."""
        pestel = _generate_pestel("Test Topic")
        assert "Political" in pestel or "政治" in pestel
        assert "Economic" in pestel or "经济" in pestel
        assert "Social" in pestel or "社会" in pestel
        assert "Technological" in pestel or "技术" in pestel
        assert "Environmental" in pestel or "环境" in pestel
        assert "Legal" in pestel or "法律" in pestel

    def test_pestel_contains_mermaid(self):
        """Test that PESTEL contains Mermaid diagram."""
        pestel = _generate_pestel("Test Topic")
        assert "```mermaid" in pestel
        assert "mindmap" in pestel

    def test_pestel_contains_table(self):
        """Test that PESTEL contains analysis table."""
        pestel = _generate_pestel("Test Topic")
        assert "|" in pestel
        assert "影响评估" in pestel or "Impact" in pestel

    def test_pestel_contains_executive_insight(self):
        """Test that PESTEL contains Executive Insight."""
        pestel = _generate_pestel("Test Topic")
        assert "**Executive Insight:**" in pestel


class TestPorterFramework:
    """Test Porter's Five Forces analysis generation."""

    def test_porter_contains_five_forces(self):
        """Test that Porter contains all five forces."""
        porter = _generate_porter("Test Industry")
        assert "竞争" in porter or "Competition" in porter
        assert "新进入者" in porter or "New Entrants" in porter or "entrant" in porter.lower()
        assert "替代" in porter or "Substitute" in porter
        assert "供应商" in porter or "Supplier" in porter
        assert "买方" in porter or "Buyer" in porter

    def test_porter_contains_flowchart(self):
        """Test that Porter contains Mermaid flowchart."""
        porter = _generate_porter("Test Industry")
        assert "```mermaid" in porter
        assert "flowchart" in porter

    def test_porter_contains_quadrant_chart(self):
        """Test that Porter contains quadrant chart."""
        porter = _generate_porter("Test Industry")
        assert "quadrantChart" in porter


class TestSWOTFramework:
    """Test SWOT analysis generation."""

    def test_swot_contains_all_quadrants(self):
        """Test that SWOT contains all four quadrants."""
        swot = _generate_swot("Test Company")
        assert "Strengths" in swot or "优势" in swot
        assert "Weaknesses" in swot or "劣势" in swot
        assert "Opportunities" in swot or "机会" in swot
        assert "Threats" in swot or "威胁" in swot

    def test_swot_contains_visual_indicators(self):
        """Test that SWOT uses visual indicators."""
        swot = _generate_swot("Test Company")
        # Should contain indicator symbols
        assert INDICATORS['strength'] in swot
        assert INDICATORS['weakness'] in swot
        assert INDICATORS['opportunity'] in swot
        assert INDICATORS['threat'] in swot

    def test_swot_contains_strategy_matrix(self):
        """Test that SWOT contains strategy combination matrix."""
        swot = _generate_swot("Test Company")
        assert "SO" in swot
        assert "WO" in swot
        assert "ST" in swot
        assert "WT" in swot

    def test_swot_follows_pyramid_principle(self):
        """Test that SWOT follows pyramid principle (conclusion first)."""
        swot = _generate_swot("Test Company")
        # Core conclusion should appear early
        assert "核心结论" in swot or "金字塔原理" in swot


class TestValueChainFramework:
    """Test Value Chain analysis generation."""

    def test_valuechain_contains_activities(self):
        """Test that Value Chain contains key activities."""
        vc = _generate_valuechain("Test Company")
        assert "物流" in vc or "logistics" in vc.lower()
        assert "运营" in vc or "operations" in vc.lower()
        assert "营销" in vc or "marketing" in vc.lower()
        assert "服务" in vc or "service" in vc.lower()

    def test_valuechain_contains_flowchart(self):
        """Test that Value Chain contains Mermaid flowchart."""
        vc = _generate_valuechain("Test Company")
        assert "```mermaid" in vc
        assert "flowchart" in vc

    def test_valuechain_contains_optimization_path(self):
        """Test that Value Chain contains optimization recommendations."""
        vc = _generate_valuechain("Test Company")
        assert "优化" in vc or "改进" in vc or "提升" in vc


class Test5W2HFramework:
    """Test 5W2H action framework generation."""

    def test_5w2h_contains_all_dimensions(self):
        """Test that 5W2H contains all seven dimensions."""
        action = _generate_5w2h("Test Initiative")
        assert "What" in action
        assert "Why" in action
        assert "Who" in action
        assert "When" in action
        assert "Where" in action
        assert "How" in action
        assert "How Much" in action or "How much" in action

    def test_5w2h_contains_gantt_chart(self):
        """Test that 5W2H contains Gantt chart."""
        action = _generate_5w2h("Test Initiative")
        assert "```mermaid" in action
        assert "gantt" in action

    def test_5w2h_contains_golden_circle(self):
        """Test that 5W2H contains Golden Circle."""
        action = _generate_5w2h("Test Initiative")
        assert "Golden Circle" in action or "Why-How-What" in action or "WHY" in action

    def test_5w2h_contains_risk_matrix(self):
        """Test that 5W2H contains risk assessment."""
        action = _generate_5w2h("Test Initiative")
        assert "风险" in action or "Risk" in action


class TestBCGMatrix:
    """Test BCG Matrix analysis generation."""

    def test_bcg_contains_quadrants(self):
        """Test that BCG contains all four quadrants."""
        bcg = _generate_bcg_matrix("Test Company")
        assert "明星" in bcg or "Star" in bcg
        assert "金牛" in bcg or "Cash Cow" in bcg
        assert "问题" in bcg or "Question" in bcg
        assert "瘦狗" in bcg or "Dog" in bcg

    def test_bcg_contains_quadrant_chart(self):
        """Test that BCG contains quadrant chart."""
        bcg = _generate_bcg_matrix("Test Company")
        assert "```mermaid" in bcg
        assert "quadrantChart" in bcg

    def test_bcg_contains_strategy_recommendations(self):
        """Test that BCG contains strategy recommendations."""
        bcg = _generate_bcg_matrix("Test Company")
        assert "战略建议" in bcg or "Strategy" in bcg


class TestFullReportGeneration:
    """Test full report generation."""

    def test_generate_consulting_report_external(self):
        """Test generating report with external context."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output = os.path.join(tmpdir, "external.md")
            result = generate_consulting_report(
                topic="市场宏观环境分析",
                output=output,
                context="external"
            )

            assert "generated" in result.lower()
            content = Path(output).read_text(encoding="utf-8")
            assert "PESTEL" in content
            assert "Porter" in content

    def test_generate_consulting_report_competitive(self):
        """Test generating report with competitive context."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output = os.path.join(tmpdir, "competitive.md")
            result = generate_consulting_report(
                topic="竞争态势分析",
                output=output,
                context="competitive"
            )

            content = Path(output).read_text(encoding="utf-8")
            assert "SWOT" in content
            assert "BCG" in content

    def test_generate_consulting_report_action(self):
        """Test generating report with action context."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output = os.path.join(tmpdir, "action.md")
            result = generate_consulting_report(
                topic="执行方案",
                output=output,
                context="action"
            )

            content = Path(output).read_text(encoding="utf-8")
            assert "5W2H" in content
            assert "gantt" in content

    def test_generate_consulting_report_auto_context(self):
        """Test auto context detection in report generation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output = os.path.join(tmpdir, "auto.md")
            # Should auto-detect as external
            result = generate_consulting_report(
                topic="Market macro environment",
                output=output
            )

            content = Path(output).read_text(encoding="utf-8")
            assert "PESTEL" in content

    def test_generate_pestel_report(self):
        """Test PESTEL-specific report generation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output = os.path.join(tmpdir, "pestel.md")
            result = generate_pestel_report(topic="Test Topic", output=output)

            assert "generated" in result.lower()
            content = Path(output).read_text(encoding="utf-8")
            assert "PESTEL" in content

    def test_generate_porter_report(self):
        """Test Porter-specific report generation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output = os.path.join(tmpdir, "porter.md")
            result = generate_porter_report(industry="Technology", output=output)

            content = Path(output).read_text(encoding="utf-8")
            assert "Five Forces" in content or "五力" in content

    def test_generate_swot_report(self):
        """Test SWOT-specific report generation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output = os.path.join(tmpdir, "swot.md")
            result = generate_swot_report(subject="Apple Inc", output=output)

            content = Path(output).read_text(encoding="utf-8")
            assert "SWOT" in content
            assert "Apple Inc" in content

    def test_generate_valuechain_report(self):
        """Test Value Chain-specific report generation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output = os.path.join(tmpdir, "valuechain.md")
            result = generate_valuechain_report(company="Amazon", output=output)

            content = Path(output).read_text(encoding="utf-8")
            assert "价值链" in content or "Value Chain" in content
            assert "Amazon" in content

    def test_generate_action_report(self):
        """Test action plan report generation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output = os.path.join(tmpdir, "action.md")
            result = generate_action_report(initiative="Digital Transformation", output=output)

            content = Path(output).read_text(encoding="utf-8")
            assert "5W2H" in content
            assert "Digital Transformation" in content

    def test_generate_demo_report(self):
        """Test demo report generation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output = os.path.join(tmpdir, "demo.md")
            result = generate_demo_report(output=output)

            assert "generated" in result.lower()
            content = Path(output).read_text(encoding="utf-8")
            assert "新能源汽车" in content


class TestReportQuality:
    """Test report quality and formatting."""

    def test_report_has_proper_headers(self):
        """Test that reports have proper Markdown headers."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output = os.path.join(tmpdir, "headers.md")
            generate_consulting_report(topic="Test", output=output)

            content = Path(output).read_text(encoding="utf-8")
            assert "# " in content  # H1
            assert "## " in content  # H2

    def test_report_has_frontmatter(self):
        """Test that reports have YAML frontmatter."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output = os.path.join(tmpdir, "frontmatter.md")
            generate_consulting_report(topic="Test", output=output)

            content = Path(output).read_text(encoding="utf-8")
            assert content.startswith("---")
            assert "methodology" in content.lower()

    def test_report_has_mece_reference(self):
        """Test that reports reference MECE principle."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output = os.path.join(tmpdir, "mece.md")
            generate_consulting_report(topic="Test", output=output)

            content = Path(output).read_text(encoding="utf-8")
            assert "MECE" in content

    def test_report_has_multiple_mermaid_diagrams(self):
        """Test that reports have multiple Mermaid diagrams."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output = os.path.join(tmpdir, "mermaid.md")
            generate_demo_report(output=output)

            content = Path(output).read_text(encoding="utf-8")
            mermaid_count = content.count("```mermaid")
            assert mermaid_count >= 3

    def test_report_has_executive_insights(self):
        """Test that reports have Executive Insight callouts."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output = os.path.join(tmpdir, "insights.md")
            generate_demo_report(output=output)

            content = Path(output).read_text(encoding="utf-8")
            insight_count = content.count("**Executive Insight:**")
            assert insight_count >= 2

    def test_report_has_visual_separation(self):
        """Test that reports have visual separation (dividers)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output = os.path.join(tmpdir, "dividers.md")
            generate_consulting_report(topic="Test", output=output)

            content = Path(output).read_text(encoding="utf-8")
            assert "---" in content


class TestMethodologyCompliance:
    """Test methodology compliance."""

    def test_pyramid_principle_conclusion_first(self):
        """Test that conclusions appear before supporting analysis."""
        swot = _generate_swot("Test")
        # The "核心结论" should appear early in the section
        conclusion_pos = swot.find("核心结论")
        detail_pos = swot.find("### 优势分析")
        if conclusion_pos >= 0 and detail_pos >= 0:
            assert conclusion_pos < detail_pos

    def test_insight_driven_headlines(self):
        """Test that headlines are insight-driven, not descriptive."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output = os.path.join(tmpdir, "headlines.md")
            generate_demo_report(output=output)

            content = Path(output).read_text(encoding="utf-8")
            # Should have insight-driven headlines like "战略态势诊断" not just "SWOT分析"
            assert "诊断" in content or "深度" in content or "解构" in content
