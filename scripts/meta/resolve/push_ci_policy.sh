#!/usr/bin/env bash
set -euo pipefail

: "${GITHUB_EVENT_CREATED:?Missing GITHUB_EVENT_CREATED}"
: "${GITHUB_OUTPUT:?Missing GITHUB_OUTPUT}"
: "${GITHUB_SHA:?Missing GITHUB_SHA}"
: "${GITHUB_REF:?Missing GITHUB_REF}"
: "${GH_TOKEN:?Missing GH_TOKEN}"
: "${GITHUB_REPOSITORY:?Missing GITHUB_REPOSITORY}"

if [[ "${GITHUB_REF}" == "refs/heads/main" && "${CI_RUN_ON_MAIN:-}" != "true" ]]; then
	{
		echo "should_run=false"
		echo "skip_reason=main-push-gated-by-ci-run-on-main"
		echo "commit_in_main=true"
	} >>"${GITHUB_OUTPUT}"
	echo "Push to main detected and repository variable CI_RUN_ON_MAIN is not 'true' -> CI will be skipped."
	exit 0
fi

if [[ "${GITHUB_REF}" != "refs/heads/main" ]]; then
	branch_name="${GITHUB_REF#refs/heads/}"
	case "${branch_name}" in
	update/* | alert-autofix-*) max_attempts=10 ;;
	*) max_attempts=1 ;;
	esac
	attempt=0
	pr_count=0
	while ((attempt < max_attempts)); do
		pr_count="$(gh pr list --repo "${GITHUB_REPOSITORY}" --head "${branch_name}" --state open --json number --jq 'length')"
		if ((pr_count > 0)); then
			break
		fi
		attempt=$((attempt + 1))
		if ((attempt < max_attempts)); then
			sleep 2
		fi
	done
	if ((pr_count > 0)); then
		{
			echo "should_run=false"
			echo "skip_reason=pr-ci-covers-this-push"
			echo "commit_in_main=false"
		} >>"${GITHUB_OUTPUT}"
		echo "Open PR exists for branch '${branch_name}' -> CI will be skipped; pull_request workflow handles this push."
		exit 0
	fi
fi

if [[ "${GITHUB_EVENT_CREATED}" != "true" ]]; then
	{
		echo "should_run=true"
		echo "skip_reason=not-a-branch-creation"
		echo "commit_in_main=false"
	} >>"${GITHUB_OUTPUT}"
	echo "Regular push detected -> CI will run."
	exit 0
fi

if git merge-base --is-ancestor "${GITHUB_SHA}" "origin/main"; then
	{
		echo "should_run=false"
		echo "skip_reason=branch-created-from-commit-already-in-main"
		echo "commit_in_main=true"
	} >>"${GITHUB_OUTPUT}"
	echo "Branch creation detected and commit ${GITHUB_SHA} is already contained in origin/main -> CI will be skipped."
else
	{
		echo "should_run=true"
		echo "skip_reason=branch-created-from-commit-not-in-main"
		echo "commit_in_main=false"
	} >>"${GITHUB_OUTPUT}"
	echo "Branch creation detected and commit ${GITHUB_SHA} is not contained in origin/main -> CI will run."
fi
