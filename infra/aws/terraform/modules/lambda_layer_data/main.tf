###############################################################################
# Lambda layer module: data_libs
#
# Packages heavy data-library deps (pandas + pyarrow + numpy + Faker) as a
# Lambda layer, so individual function packages stay slim. Each Lambda's
# unzipped runtime size is capped at 250 MB; layers get their OWN 250 MB cap.
# Together: 500 MB of total room for function + layer.
#
# Why this matters: pandas + pyarrow + numpy alone are ~150 MB unzipped, plus
# their transitive deps push over 250 MB when bundled with snowflake-connector
# in a single Lambda. The layer pattern separates concerns cleanly.
###############################################################################

locals {
  layer_name        = "${var.project_name}-${var.environment}-data-libs"
  source_dir        = abspath("${path.module}/../../../lambdas/_layers/data_libs")
  build_dir         = abspath("${path.module}/.build")
  package_path      = abspath("${path.module}/.build/data_libs_layer.zip")
  s3_key            = "lambda_layers/data_libs.zip"
}

###############################################################################
# Build the layer zip
#
# Layer convention: deps must be installed under python/ in the zip.
# Lambda extracts to /opt/python/, which is on the Python path automatically.
###############################################################################

resource "null_resource" "build_layer" {
  triggers = {
    requirements_hash = filesha256("${local.source_dir}/requirements.txt")
  }

  provisioner "local-exec" {
    command = <<-EOT
      set -e
      rm -rf ${local.build_dir}
      mkdir -p ${local.build_dir}/python

      PYTHONNOUSERSITE=1 python3 -m pip install \
        --isolated \
        --target ${local.build_dir}/python \
        --platform manylinux2014_x86_64 \
        --python-version 3.12 \
        --only-binary=:all: \
        --implementation cp \
        -r ${local.source_dir}/requirements.txt

      # ---- Slim the layer to fit Lambda's 250 MB unzipped cap ----
      # pyarrow is ~190 MB unzipped; it ships subsystems we don't use.
      # Standard trim list — stable across pyarrow versions.
      cd ${local.build_dir}/python

      # Tests directories across all packages (never needed at runtime)
      find . -type d -name 'tests' -exec rm -rf {} + 2>/dev/null || true
      find . -type d -name 'test'  -exec rm -rf {} + 2>/dev/null || true

      # pyarrow-specific unused subsystems
      rm -rf pyarrow/include 2>/dev/null || true
      rm -rf pyarrow/flight* 2>/dev/null || true
      rm -rf pyarrow/gandiva* 2>/dev/null || true
      rm -rf pyarrow/substrait* 2>/dev/null || true
      rm -rf pyarrow/_orc* 2>/dev/null || true
      rm -rf pyarrow/orc* 2>/dev/null || true
      rm -rf pyarrow/_flight* 2>/dev/null || true
      rm -rf pyarrow/_substrait* 2>/dev/null || true
      rm -rf pyarrow/_gandiva* 2>/dev/null || true

      # pandas tests + sample data
      rm -rf pandas/tests 2>/dev/null || true

      # Compiled cache + bytecode (always regenerable, just bloat)
      find . -name '*.pyc' -delete 2>/dev/null || true
      find . -type d -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true

      # Documentation that some packages ship
      find . -type d -name 'docs' -exec rm -rf {} + 2>/dev/null || true

      # ---- Verify final size before zipping ----
      echo "----- Layer size after pruning -----"
      du -sh ${local.build_dir}/python

      # Now zip
      cd ${local.build_dir} && zip -r ${local.package_path} python -q

      ls -lh ${local.package_path}

      aws s3 cp ${local.package_path} s3://${var.artifacts_bucket}/${local.s3_key}
    EOT
  }
}

###############################################################################
# Track the S3 object as a real Terraform resource so the layer version
# resource can declare a proper dependency on it (not relying on provisioner
# side effects, which are invisible to Terraform's dep graph).
###############################################################################

resource "aws_s3_object" "layer_package" {
  bucket = var.artifacts_bucket
  key    = local.s3_key
  source = local.package_path

  # Hash the INPUT requirements.txt (exists at plan time) rather than the
  # zip artifact (doesn't exist until null_resource.build_layer runs).
  # If requirements change, this hash changes -> S3 object is updated.
  etag = filemd5("${local.source_dir}/requirements.txt")

  depends_on = [null_resource.build_layer]
}

###############################################################################
# Publish the layer version
#
# Each time we update requirements.txt and re-apply, a new layer version is
# published. The Lambda functions attach to the LATEST version via the
# layer_arn output below.
###############################################################################

resource "aws_lambda_layer_version" "this" {
  layer_name          = local.layer_name
  description         = "Data libs (pandas + pyarrow + numpy + Faker) for csa Lambdas"
  s3_bucket           = aws_s3_object.layer_package.bucket
  s3_key              = aws_s3_object.layer_package.key
  source_code_hash = filebase64sha256("${local.source_dir}/requirements.txt")

  compatible_runtimes = ["python3.12"]
  compatible_architectures = ["x86_64"]
}
