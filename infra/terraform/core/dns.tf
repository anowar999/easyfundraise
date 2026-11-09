# A record efcore.doctra.ai -> core Elastic IP. Needs an existing Route53 hosted
# zone for doctra.ai in this account. Set manage_dns = false to skip (e.g. if DNS
# lives elsewhere) and create the record by hand.
data "aws_route53_zone" "this" {
  count = var.manage_dns ? 1 : 0
  name  = var.hosted_zone_name
}

resource "aws_route53_record" "core" {
  count   = var.manage_dns ? 1 : 0
  zone_id = data.aws_route53_zone.this[0].zone_id
  name    = var.domain_name
  type    = "A"
  ttl     = 300
  records = [aws_eip.core.public_ip]
}
