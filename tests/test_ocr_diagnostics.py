import unittest
from audit_ocr_pilot import normalize_latex


class FormulaDiagnosticTests(unittest.TestCase):
    def test_critical_math_symbols_are_not_erased(self):
        pairs=[('P(A|B)','P(B|A)'),(r'P(\bar B)',r'P(B)'),
               (r'x\le1',r'x<1'),(r'A\cup B',r'A\cap B'),
               (r'P(B_i)',r'P(B_j)'),('0.0004','0.004')]
        for a,b in pairs:
            with self.subTest(a=a,b=b):self.assertNotEqual(normalize_latex(a),normalize_latex(b))


if __name__=='__main__':unittest.main()
