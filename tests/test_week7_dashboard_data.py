from eval.week7.dashboard_data import load_race_sets, render_markdown


def test_load_race_sets_finds_the_assignment_race_and_skips_hard():
    sets = load_race_sets()
    keys = [s["key"] for s in sets]
    assert "assignment" in keys
    assert "easy" in keys
    assert "medium" in keys
    assert "hard" not in keys  # not run this session -- must not appear as empty


def test_each_race_set_has_agent_and_workflow_rows():
    sets = load_race_sets()
    assignment = next(s for s in sets if s["key"] == "assignment")
    systems = {row["system"] for row in assignment["rows"]}
    assert systems == {"agent", "workflow"}


def test_question_breakdown_merges_agent_and_workflow_by_id():
    sets = load_race_sets()
    assignment = next(s for s in sets if s["key"] == "assignment")
    assert len(assignment["questions"]) == 10
    row = assignment["questions"][0]
    assert "agent_passed" in row
    assert "workflow_passed" in row
    assert "question" in row


def test_render_markdown_handles_headers_bold_and_bullets():
    html = render_markdown("## A Header\n\nSome **bold** and `code` text.\n\n- item one\n- item two\n")
    assert "<h3>A Header</h3>" in html
    assert "<strong>bold</strong>" in html
    assert "<code>code</code>" in html
    assert "<li>item one</li>" in html
    assert "<li>item two</li>" in html


def test_render_markdown_skips_table_rows_and_top_level_title():
    html = render_markdown("# Verdict\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\nReal prose.\n")
    assert "Verdict" not in html
    assert "|" not in html
    assert "<p>Real prose.</p>" in html
