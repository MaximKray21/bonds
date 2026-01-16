import os
from t_tech.invest import Client
from t_tech.invest.schemas import (
    AssetsRequest,
    InstrumentType,
    GetBondEventsRequest,
    EventType,
    Quotation,
)
import typing as tp
import datetime

token_path = "/home/kgms-dev-vm-1/tokens/t-tech-investments-token.txt"
os.environ["TOKEN"] = open(token_path, "r").read()
TOKEN = os.environ["TOKEN"]


def money_to_value(money_class):
    return money_class.units + float(f"0.{money_class.nano}")


class Bond:
    """
    Получаем свой кастомный класс для работы бондами
    """

    def __init__(self, asset_uid, instrument_id, maturity_date):
        """
        Args:
            asset_uid: Идентификатор актива.
            instrument_id: Идентификатор инструмента.
            maturity_date: дата погашения.
        """

        self.asset_uid = asset_uid
        """asset_uid: Идентификатор актива."""

        self.instrument_id = instrument_id
        """..."""

        self.nominal_value = self.bond_nominal()
        """Значение номинала"""

        self.cur_price_value = self.cur_price()
        """Значение текущей цены"""

        self.accumulated_coupon_income = self.nkd()
        """Значение НКД"""

        if self.call_option():
            self.maturity_date = (
                maturity_date
                if maturity_date < self.call_option()[-1]
                else self.call_option()
            )
        else:
            self.maturity_date = maturity_date

    def __quotation_to_value(self, quotation_class):
        """служебная"""
        return quotation_class.units + float(f"0.{quotation_class.nano}")

    def bond_nominal(self, is_value: bool = True) -> tp.Union[float, Quotation]:
        """получаем значение номинала"""
        with Client(TOKEN[:-1]) as client:
            r = client.instruments.get_asset_by(id=self.asset_uid)
            nominal_quotation = r.asset.security.bond.current_nominal
            return (
                self.__quotation_to_value(nominal_quotation)
                if is_value
                else nominal_quotation
            )

    def cur_price(self) -> float:
        """получаем цену облигации"""
        with Client(TOKEN[:-1]) as client:
            r = client.market_data.get_last_prices(
                instrument_id=(
                    self.instrument_id
                    if isinstance(self.instrument_id, list)
                    else [self.instrument_id]
                )
            )
            if self.nominal_value:
                return (
                    (
                        r.last_prices[-1].price.units
                        + float(f"0.{r.last_prices[-1].price.nano}")
                    )
                    / 100
                    * self.nominal_value
                )
            else:
                self.nominal_value = self.bond_nominal(self.asset_uid)
                return (
                    (
                        r.last_prices[-1].price.units
                        + float(f"0.{r.last_prices[-1].price.nano}")
                    )
                    / 100
                    * self.nominal_value
                )

    def nkd(self, is_value: bool = True) -> tp.Union[float, Quotation]:
        """получаем НКД"""
        with Client(TOKEN[:-1]) as client:
            r = client.instruments.get_accrued_interests(
                instrument_id=self.instrument_id
            )
            for item in r.accrued_interests:
                if datetime.datetime.now().date() == item.date.date():
                    return (
                        self.__quotation_to_value(item.value)
                        if is_value
                        else item.value
                    )

    def coupons(self):
        """получаем ивенты по купонам"""
        with Client(TOKEN[:-1]) as client:
            for event_type in EventType:
                if event_type == EventType.EVENT_TYPE_CPN:
                    r = client.instruments.get_bond_events(
                        request=GetBondEventsRequest(
                            instrument_id=self.instrument_id,
                            type=event_type,
                        )
                    )
                    return r.events

    def call_option(self):
        """тут мы получаем дату оферты"""
        with Client(TOKEN[:-1]) as client:
            for event_type in EventType:
                if event_type == EventType.EVENT_TYPE_CALL:
                    r = client.instruments.get_bond_events(
                        request=GetBondEventsRequest(
                            instrument_id=self.instrument_id,
                            type=event_type,
                        )
                    )
                    return r.events


class Profitability:
    """
    Доходность к погашению/оферте без реинвестирования
    """

    class PurchaseCosts:
        """
        затраты на покупку. Сумма цены бонда и НКД
        """

        def __init__(self, bond):
            """
            Args:
                bond: кастомная облигация.
            """
            self.bond = bond
            self.value = self.bond.cur_price() + self.bond.accumulated_coupon_income

    class RepaymentAmount:
        """
        Доход к погашению/оферте без реинвестирования с вычетом налога
        """

        def __init__(self, bond):
            """
            Args:
                bond: кастомная облигация.
            """
            self.bond = bond
            self.value = self.minus_tax()

        def coupons_total(self):
            """Доход от купонов"""
            coupons_list = self.bond.coupons()
            total = sum(
                map(
                    lambda event: money_to_value(event.pay_one_bond),
                    filter(
                        lambda event: event.event_date.date()
                        > datetime.datetime.now().date(),
                        coupons_list,
                    ),
                )
            )
            return total

        def discont(self):
            """Дисконт"""
            return self.bond.nominal_value - self.bond.cur_price()

        def minus_tax(self, tax=0.13):
            """вычет налога"""
            return (self.coupons_total() + self.discont()) * (1.0 - tax)

    def profitability(self):
        """Доходность"""
        # прибыль
        gain = self.repayment_amount.value - self.purchase_costs.value
        # прибыль в процентах
        gain_p = gain / self.purchase_costs.value * 100
        # доходность
        profit = (
            gain_p
            / (datetime.datetime.now().date() - self.bond.maturity_date.date()).days
            * 365
        )
        return profit

    def __init__(self, bond):
        self.bond = bond

        # 1. расходы на покупку
        self.purchase_costs = self.PurchaseCosts(bond)
        # 2. сумма к погашению
        self.repayment_amount = self.RepaymentAmount(bond)
        # 3. доходность к погашению
        self.profitability_value = self.profitability()


def main():
    with Client(TOKEN[:-1]) as client:
        r = client.instruments.get_assets(
            request=AssetsRequest(instrument_type=InstrumentType.INSTRUMENT_TYPE_BOND)
        )
        print("BONDS")
        for bond in r.assets:
            print(bond)
            break

        r = client.instruments.get_asset_by(id=bond.uid)
    asset_uid = r.asset.uid
    instrument_id = r.asset.instruments[-1].uid
    maturity_date_ = r.asset.security.bond.maturity_date
    bond_ = Bond(asset_uid, instrument_id, maturity_date_)
    PROFITABILITY = Profitability(bond_)
    print("PROFITABILITY: {}".format(PROFITABILITY.profitability_value))


if __name__ == "__main__":
    main()
