# Customer Spend Analytics — AWS deployment Makefile
# Smart Mode with persistent / ephemeral stack separation
#
# DAILY WORKFLOW:
#   make session-start   # at start of work (~3 min, costs start)
#   <work, develop, test, screenshot>
#   make session-end     # at end of work (~2 min, costs stop)
#
# RARE OPERATIONS:
#   make bootstrap            # ONCE — Terraform state backend
#   make persistent-apply     # ONCE (and after persistent module changes)
#   make persistent-destroy   # ONLY when permanently abandoning project
#
# MONITORING:
#   make verify-clean         # confirm nothing's running you don't expect
#   make cost-mtd             # month-to-date cost
#   make cost-budget          # budget vs actual

PERSISTENT_DIR := terraform/envs/dev/persistent
EPHEMERAL_DIR  := terraform/envs/dev/ephemeral
BOOTSTRAP_DIR  := 0_bootstrap

AWS_ACCOUNT_ID := $(shell aws sts get-caller-identity --query Account --output text)

# ─────────────────────────────────────────────────────────────────────────────
# Help
# ─────────────────────────────────────────────────────────────────────────────
.PHONY: help
help:
	@echo "Customer Spend Analytics — AWS (Smart Mode + Persistent/Ephemeral)"
	@echo ""
	@echo "DAILY:"
	@echo "  session-start              Start a work session (ephemeral apply)"
	@echo "  session-end                End a work session (ephemeral destroy)"
	@echo ""
	@echo "PERSISTENT (rarely changed):"
	@echo "  persistent-init            Initialize persistent stack"
	@echo "  persistent-plan            Preview persistent changes"
	@echo "  persistent-apply           Deploy persistent stack"
	@echo "  persistent-output          Show persistent outputs"
	@echo "  persistent-destroy         ⚠ Tear down all stateful resources"
	@echo ""
	@echo "EPHEMERAL (every session):"
	@echo "  ephemeral-init             Initialize ephemeral stack"
	@echo "  ephemeral-plan             Preview ephemeral changes"
	@echo "  ephemeral-apply            Deploy ephemeral stack"
	@echo "  ephemeral-output           Show ephemeral outputs"
	@echo "  ephemeral-destroy          Tear down ephemeral compute"
	@echo ""
	@echo "BOOTSTRAP (one-time):"
	@echo "  bootstrap                  Create the Terraform state backend"
	@echo ""
	@echo "MONITORING:"
	@echo "  verify-clean               Confirm no csa-dev-* compute is running"
	@echo "  cost-mtd                   Month-to-date AWS cost"
	@echo "  cost-yesterday             Yesterday's cost"
	@echo "  cost-budget                Budget vs actual"
	@echo ""
	@echo "UTILITIES:"
	@echo "  fmt                        Format all .tf files"
	@echo "  validate                   Validate Terraform syntax"
	@echo ""

# ─────────────────────────────────────────────────────────────────────────────
# Bootstrap (one-time)
# ─────────────────────────────────────────────────────────────────────────────
.PHONY: bootstrap
bootstrap:
	@echo "→ Bootstrap: creating Terraform state backend (run ONCE per account)..."
	cd $(BOOTSTRAP_DIR) && terraform init && terraform apply

# ─────────────────────────────────────────────────────────────────────────────
# Persistent stack
# ─────────────────────────────────────────────────────────────────────────────
.PHONY: persistent-init persistent-plan persistent-apply persistent-output persistent-destroy
persistent-init:
	@echo "→ Initializing persistent stack..."
	cd $(PERSISTENT_DIR) && terraform init

persistent-plan:
	cd $(PERSISTENT_DIR) && terraform plan

persistent-apply:
	@echo "→ Deploying persistent stack (stateful resources)..."
	cd $(PERSISTENT_DIR) && terraform apply

persistent-output:
	cd $(PERSISTENT_DIR) && terraform output

persistent-destroy:
	@echo "⚠  TEARING DOWN PERSISTENT STACK"
	@echo "   This removes S3 buckets (and ALL data in them),"
	@echo "   Secrets Manager entries, IAM roles, and ECR repos."
	@echo "   Only do this if permanently abandoning the project."
	@echo "   Press Ctrl+C in 10 seconds to cancel..."
	@sleep 10
	cd $(PERSISTENT_DIR) && terraform destroy

# ─────────────────────────────────────────────────────────────────────────────
# Ephemeral stack
# ─────────────────────────────────────────────────────────────────────────────
.PHONY: ephemeral-init ephemeral-plan ephemeral-apply ephemeral-output ephemeral-destroy
ephemeral-init:
	@echo "→ Initializing ephemeral stack..."
	cd $(EPHEMERAL_DIR) && terraform init

ephemeral-plan:
	cd $(EPHEMERAL_DIR) && terraform plan

ephemeral-apply:
	@echo "→ Deploying ephemeral stack (compute)..."
	cd $(EPHEMERAL_DIR) && terraform apply

ephemeral-output:
	cd $(EPHEMERAL_DIR) && terraform output

ephemeral-destroy:
	@echo "→ Destroying ephemeral compute (persistent data stays)..."
	cd $(EPHEMERAL_DIR) && terraform destroy

# ─────────────────────────────────────────────────────────────────────────────
# Session helpers — these are what you'll use every day
# ─────────────────────────────────────────────────────────────────────────────
.PHONY: session-start session-end
session-start: ephemeral-apply
	@echo ""
	@echo "═══════════════════════════════════════════════════════════════"
	@echo "✓ Work session started"
	@echo "═══════════════════════════════════════════════════════════════"
	@echo ""
	@$(MAKE) cost-budget

session-end: ephemeral-destroy verify-clean
	@echo ""
	@$(MAKE) cost-mtd
	@echo ""
	@echo "═══════════════════════════════════════════════════════════════"
	@echo "✓ Work session ended — costs back to ~$$1/month"
	@echo "═══════════════════════════════════════════════════════════════"

# ─────────────────────────────────────────────────────────────────────────────
# Monitoring
# ─────────────────────────────────────────────────────────────────────────────
.PHONY: verify-clean cost-mtd cost-yesterday cost-budget
verify-clean:
	@echo "→ Verifying clean state (no ephemeral resources should appear)..."
	@echo ""
	@echo "── Lambda functions ──"
	@aws lambda list-functions --query 'Functions[?starts_with(FunctionName, `csa-dev`)].FunctionName' --output text | tr '\t' '\n' | sed 's/^/  /' || echo "  ✓ none"
	@echo ""
	@echo "── EMR Serverless apps ──"
	@aws emr-serverless list-applications --query 'applications[?starts_with(name, `csa-dev`)].[name,state]' --output table 2>/dev/null || echo "  ✓ none"
	@echo ""
	@echo "── Step Functions state machines ──"
	@aws stepfunctions list-state-machines --query 'stateMachines[?starts_with(name, `csa-dev`)].name' --output text | tr '\t' '\n' | sed 's/^/  /' || echo "  ✓ none"
	@echo ""
	@echo "── ECS services ──"
	@aws ecs list-clusters --query 'clusterArns[?contains(@, `csa-dev`)]' --output text | tr '\t' '\n' | sed 's/^/  /' || echo "  ✓ none"
	@echo ""
	@echo "── Load balancers ──"
	@aws elbv2 describe-load-balancers --query 'LoadBalancers[?starts_with(LoadBalancerName, `csa-dev`)].LoadBalancerName' --output text 2>/dev/null | tr '\t' '\n' | sed 's/^/  /' || echo "  ✓ none"
	@echo ""
	@echo "Tip: persistent resources (S3, Secrets, IAM, ECR) are EXPECTED to stay."

cost-mtd:
	@echo "→ Month-to-date cost by service (>$$0.01 only):"
	@aws ce get-cost-and-usage \
	  --time-period Start=$$(date -v1d +%Y-%m-%d),End=$$(date +%Y-%m-%d) \
	  --granularity MONTHLY \
	  --metrics UnblendedCost \
	  --group-by Type=DIMENSION,Key=SERVICE \
	  --query 'ResultsByTime[0].Groups[].[Keys[0],Metrics.UnblendedCost.Amount]' \
	  --output table

cost-yesterday:
	@echo "→ Yesterday's cost by service:"
	@aws ce get-cost-and-usage \
	  --time-period Start=$$(date -v-1d +%Y-%m-%d),End=$$(date +%Y-%m-%d) \
	  --granularity DAILY \
	  --metrics UnblendedCost \
	  --group-by Type=DIMENSION,Key=SERVICE \
	  --query 'ResultsByTime[0].Groups[?Metrics.UnblendedCost.Amount>`0.001`].[Keys[0],Metrics.UnblendedCost.Amount]' \
	  --output table

cost-budget:
	@echo "→ Current budget vs actual:"
	@aws budgets describe-budgets \
	  --account-id $(AWS_ACCOUNT_ID) \
	  --query 'Budgets[].[BudgetName,BudgetLimit.Amount,CalculatedSpend.ActualSpend.Amount,CalculatedSpend.ForecastedSpend.Amount]' \
	  --output table

# ─────────────────────────────────────────────────────────────────────────────
# Utilities
# ─────────────────────────────────────────────────────────────────────────────
.PHONY: fmt validate
fmt:
	terraform fmt -recursive .

validate:
	cd $(PERSISTENT_DIR) && terraform validate
	cd $(EPHEMERAL_DIR) && terraform validate
	cd $(BOOTSTRAP_DIR) && terraform validate
