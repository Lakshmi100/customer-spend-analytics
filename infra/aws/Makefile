# Customer Spend Analytics — AWS deployment Makefile
#
# Run from `infra/aws/` directory:
#   make help            # show this menu
#   make bootstrap       # create state backend (run ONCE)
#   make init            # initialize Terraform for dev env
#   make plan            # show what would change
#   make apply           # apply changes
#   make output          # show all outputs
#   make destroy         # tear down dev env (NOT bootstrap)
#   make fmt             # format all .tf files

DEV_DIR := terraform/envs/dev
BOOTSTRAP_DIR := 0_bootstrap

.PHONY: help
help:
	@echo "Customer Spend Analytics — AWS deployment"
	@echo ""
	@echo "Targets:"
	@echo "  bootstrap           Create the Terraform state backend (run once)"
	@echo "  init                Initialize Terraform for dev environment"
	@echo "  plan                Preview infrastructure changes"
	@echo "  apply               Deploy changes to AWS"
	@echo "  output              Show all stack outputs"
	@echo "  destroy             Tear down the dev environment (state backend stays)"
	@echo "  fmt                 Format Terraform files"
	@echo "  validate            Validate Terraform syntax"
	@echo ""

.PHONY: bootstrap
bootstrap:
	@echo "→ Bootstrap: creating Terraform state backend..."
	cd $(BOOTSTRAP_DIR) && terraform init && terraform apply

.PHONY: init
init:
	@echo "→ Initializing dev environment..."
	cd $(DEV_DIR) && terraform init

.PHONY: plan
plan:
	cd $(DEV_DIR) && terraform plan

.PHONY: apply
apply:
	cd $(DEV_DIR) && terraform apply

.PHONY: output
output:
	cd $(DEV_DIR) && terraform output

.PHONY: destroy
destroy:
	@echo "⚠ Tearing down dev environment (NOT the state backend)"
	@echo "  Press Ctrl+C in 5 seconds to cancel..."
	@sleep 5
	cd $(DEV_DIR) && terraform destroy

.PHONY: fmt
fmt:
	terraform fmt -recursive .

.PHONY: validate
validate:
	cd $(DEV_DIR) && terraform validate
	cd $(BOOTSTRAP_DIR) && terraform validate
