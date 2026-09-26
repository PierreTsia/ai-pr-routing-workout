"""Review threads. Counting and timelines stay in code.

Copilot, Claude, and a human reviewer are the same shape: someone asked for a
change, and a later reply or a commit on that file is a fact, not proof it was
handled.
"""

from __future__ import annotations

from dataclasses import dataclass


def is_copilot(login: str | None) -> bool:
    return bool(login) and "copilot" in login.lower()


def is_claude(login: str | None) -> bool:
    return bool(login) and "claude" in login.lower()


def is_bot(login: str | None) -> bool:
    if not login:
        return False
    lowered = login.lower()
    return lowered.endswith("[bot]") or is_copilot(login) or is_claude(login)


def is_human_reviewer(login: str | None, pull_author: str) -> bool:
    """A person, other than the pull-request author, who left a review comment."""
    return bool(login) and login != pull_author and not is_bot(login)


@dataclass(frozen=True)
class ReviewComment:
    id: int
    author: str
    body: str
    created_at: str
    path: str
    url: str

    @property
    def copilot(self) -> bool:
        return is_copilot(self.author)

    @property
    def claude(self) -> bool:
        return is_claude(self.author)


@dataclass(frozen=True)
class Commit:
    sha: str
    committed_at: str
    summary: str


@dataclass(frozen=True)
class ReviewThread:
    id: int
    path: str
    outdated: bool
    comments: tuple[ReviewComment, ...]
    later_commit_sha: str | None
    later_commit_touches_path: bool | None
    pull_author: str = ""

    @property
    def copilot(self) -> bool:
        return any(comment.copilot for comment in self.comments)

    @property
    def claude(self) -> bool:
        return any(comment.claude for comment in self.comments) and not self.copilot

    @property
    def source(self) -> str:
        if self.copilot:
            return "copilot"
        if self.claude:
            return "claude"
        return "human"

    @property
    def human_review(self) -> bool:
        """A human reviewer opened the thread. Auto-review threads stay on their own path."""
        if self.copilot or self.claude or not self.comments:
            return False
        return is_human_reviewer(self.comments[0].author, self.pull_author)

    @property
    def tracked(self) -> bool:
        return self.copilot or self.claude or self.human_review

    def _from_auto_reviewer(self, comment: ReviewComment) -> bool:
        if self.copilot:
            return comment.copilot
        if self.claude:
            return comment.claude
        return False

    @property
    def replied(self) -> bool:
        if self.copilot or self.claude:
            return any(not self._from_auto_reviewer(comment) for comment in self.comments)
        if self.human_review:
            reviewer = self.comments[0].author
            return any(comment.author != reviewer for comment in self.comments)
        return False

    @property
    def unanswered(self) -> bool:
        """The reviewer still has the last word, and no later commit landed on this path."""
        if not self.tracked or not self.comments:
            return False
        last = self.comments[-1]
        if (self.copilot or self.claude) and not self._from_auto_reviewer(last):
            return False
        if self.human_review and last.author != self.comments[0].author:
            return False
        return self.later_commit_sha is None


def _root_id(comment_id: int, parent_of: dict[int, int | None]) -> int:
    seen: set[int] = set()
    current = comment_id
    while parent_of.get(current) and current not in seen:
        seen.add(current)
        parent = parent_of[current]
        if parent is None:
            break
        current = parent
    return current


def build_threads(
    comments: list[dict],
    commits: list[Commit],
    paths_by_sha: dict[str, frozenset[str] | None],
    pull_author: str = "",
) -> tuple[ReviewThread, ...]:
    parsed: list[tuple[ReviewComment, int | None, bool]] = []
    parent_of: dict[int, int | None] = {}
    for raw in comments:
        comment_id = int(raw["id"])
        parent = raw.get("in_reply_to_id")
        parent_id = int(parent) if parent else None
        parent_of[comment_id] = parent_id
        user = raw.get("user") or {}
        parsed.append(
            (
                ReviewComment(
                    id=comment_id,
                    author=user.get("login") or "unknown",
                    body=raw.get("body") or "",
                    created_at=raw.get("created_at") or "",
                    path=raw.get("path") or "",
                    url=raw.get("html_url") or "",
                ),
                parent_id,
                raw.get("position") is None and raw.get("original_position") is not None,
            )
        )

    grouped: dict[int, list[tuple[ReviewComment, bool]]] = {}
    for comment, _parent, outdated in parsed:
        grouped.setdefault(_root_id(comment.id, parent_of), []).append((comment, outdated))

    threads: list[ReviewThread] = []
    for root_id, items in grouped.items():
        items.sort(key=lambda item: item[0].created_at)
        comments_only = tuple(comment for comment, _outdated in items)
        root_comment = next((comment for comment, _outdated in items if comment.id == root_id), comments_only[0])
        root_outdated = next(
            (outdated for comment, outdated in items if comment.id == root_comment.id),
            False,
        )
        later_sha, touches = _later_commit(comments_only, commits, paths_by_sha)
        threads.append(
            ReviewThread(
                id=root_comment.id,
                path=root_comment.path,
                outdated=root_outdated,
                comments=comments_only,
                later_commit_sha=later_sha,
                later_commit_touches_path=touches,
                pull_author=pull_author,
            )
        )
    threads.sort(key=lambda thread: thread.comments[0].created_at)
    return tuple(threads)


def _later_commit(
    comments: tuple[ReviewComment, ...],
    commits: list[Commit],
    paths_by_sha: dict[str, frozenset[str] | None],
) -> tuple[str | None, bool | None]:
    if any(comment.copilot for comment in comments):
        anchors = [comment.created_at for comment in comments if comment.copilot]
    elif any(comment.claude for comment in comments):
        anchors = [comment.created_at for comment in comments if comment.claude]
    else:
        reviewer = comments[0].author
        anchors = [comment.created_at for comment in comments if comment.author == reviewer]
    anchor = max(anchors) if anchors else comments[0].created_at
    path = comments[0].path
    chosen: Commit | None = None
    for commit in commits:
        if commit.committed_at <= anchor:
            continue
        paths = paths_by_sha.get(commit.sha)
        if paths is not None and path not in paths:
            continue
        if chosen is None or commit.committed_at < chosen.committed_at:
            chosen = commit
    if chosen is None:
        return None, None
    paths = paths_by_sha.get(chosen.sha)
    if paths is None:
        return chosen.sha, None
    return chosen.sha, path in paths


def threads_for_fan_out(threads: tuple[ReviewThread, ...], limit: int = 8) -> tuple[ReviewThread, ...]:
    """Ask about unanswered review threads first, auto-review and human alike.

    The cap is a token budget, not a judgment. Threads left out are counted in code.
    """
    tracked = [thread for thread in threads if thread.tracked]
    tracked.sort(key=lambda thread: (not thread.unanswered, thread.later_commit_sha is not None, thread.id))
    return tuple(tracked[:limit])