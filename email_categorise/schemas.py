from __future__ import annotations

TRIAGE_OUTPUT_DESCRIPTION = """    The model must respond with a single JSON object with this shape:

{
  "messages": [
    {
      "id": "GRAPH_MESSAGE_ID string, exactly as provided in the input",
      "primary_category": "one of: Urgent, Priority 1, Priority 2, Priority 3, Marketing, Informational, No reply needed, Complete, Possibly Complete",
      "secondary_categories": [
        "optional additional categories such as Complete or Possibly Complete"
      ],
      "flag": "one of: Today, Tomorrow, This week, Next week, No date, Mark as complete, or null",
      "needs_reply": true or false,
      "is_marketing": true or false,
      "is_informational": true or false,
      "mark_complete": true or false,
      "mark_possibly_complete": true or false,
      "create_task": true or false,
      "task_summary": "short one line description of the action to take, or null",
      "summary": "one or two sentence natural language summary, or null",
      "draft_reply_body": "plain text body of a reply email in the user's voice, or null"
    }
  ]
}

Rules:

- The messages array must include exactly one entry for every input message id.
- Never invent ids.
- Always include id and primary_category for every message.
- Do not output the special Processed category. The tool adds Processed automatically.
- If you are not confident that a conversation is finished, set mark_complete to false and mark_possibly_complete to true instead.
- Only set is_marketing to true for classic marketing / newsletter / promotion content.
- Only set is_informational to true for messages that convey information but do not obviously require an action.
- For messages that clearly need a response from the user, set needs_reply to true and include a draft_reply_body.
"""
