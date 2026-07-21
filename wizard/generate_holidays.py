# -*- coding: utf-8 -*-
from datetime import date, timedelta
from odoo import fields, models

class CrGenerateHolidaysWizard(models.TransientModel):
    _name = "cr.generate.holidays.wizard"
    _description = "Generar feriados CR"

    year = fields.Integer(required=True, default=lambda self: fields.Date.today().year)

    def _easter_sunday(self, year):
        a=year%19; b=year//100; c=year%100; d=b//4; e=b%4; f=(b+8)//25; g=(b-f+1)//3
        h=(19*a+b-d-g+15)%30; i=c//4; k=c%4; l=(32+2*e+2*i-h-k)%7; m=(a+11*h+22*l)//451
        month=(h+l-7*m+114)//31; day=((h+l-7*m+114)%31)+1
        return date(year, month, day)

    def action_generate(self):
        self.ensure_one()
        easter = self._easter_sunday(self.year)
        fixed = [
            (1,1,"Año Nuevo",True),(4,11,"Día de Juan Santamaría",True),(5,1,"Día Internacional del Trabajo",True),
            (7,25,"Anexión del Partido de Nicoya",True),(8,2,"Virgen de los Ángeles",False),(8,15,"Día de la Madre",True),
            (8,31,"Día de la Persona Negra y la Cultura Afrocostarricense",False),(9,15,"Independencia",True),
            (12,1,"Abolición del Ejército",False),(12,25,"Navidad",True),
        ]
        vals = [(date(self.year,m,d),n,p) for m,d,n,p in fixed]
        vals += [(easter-timedelta(days=3),"Jueves Santo",True),(easter-timedelta(days=2),"Viernes Santo",True)]
        Holiday = self.env["cr.payroll.public.holiday"]
        for hdate, name, mandatory in vals:
            if not Holiday.search_count([("date","=",hdate),("company_id","=",False)]):
                Holiday.create({"name":name,"date":hdate,"mandatory_pay":mandatory,"holiday_type":"movable" if "Santo" in name else "fixed"})
        return {"type":"ir.actions.act_window_close"}
