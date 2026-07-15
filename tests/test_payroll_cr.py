from odoo.tests.common import TransactionCase

class TestPayrollCR(TransactionCase):
    def test_legal_parameters_loaded(self):
        self.assertTrue(self.env["cr.payroll.tax.bracket"].search_count([]) >= 5)
        self.assertTrue(self.env["cr.payroll.social.contribution"].search_count([]) >= 10)

    def test_structures_loaded(self):
        codes = set(self.env["hr.payroll.structure"].search([("code", "like", "CR_")]).mapped("code"))
        self.assertTrue({"CR_MONTHLY", "CR_BIWEEKLY", "CR_WEEKLY", "CR_HOURLY", "CR_AGUINALDO", "CR_EXTRA", "CR_SETTLEMENT"}.issubset(codes))

    def test_input_types_unique(self):
        inputs = self.env["hr.payslip.input.type"].search([("code", "like", "CR_%")])
        self.assertEqual(len(inputs.mapped("code")), len(set(inputs.mapped("code"))))
