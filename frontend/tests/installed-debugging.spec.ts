import { test } from "@playwright/test";
import {
  runComparisonWorkflow,
  runSavedAnswersWorkflow,
} from "./installed-debugging-workflows";
import { runGroupsWorkflow } from "./installed-debugging-groups";
import { runReportsWorkflow } from "./installed-debugging-reports";
import { WORKFLOW_TITLES } from "./installed-debugging-support";

test(WORKFLOW_TITLES.S, async ({ page }, testInfo) => {
  await runSavedAnswersWorkflow(page, testInfo);
});

test(WORKFLOW_TITLES.C, async ({ page }, testInfo) => {
  await runComparisonWorkflow(page, testInfo);
});

test(WORKFLOW_TITLES.G, async ({ page }, testInfo) => {
  await runGroupsWorkflow(page, testInfo);
});

test(WORKFLOW_TITLES.R, async ({ page }, testInfo) => {
  await runReportsWorkflow(page, testInfo);
});
