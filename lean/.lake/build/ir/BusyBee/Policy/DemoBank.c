// Lean compiler output
// Module: BusyBee.Policy.DemoBank
// Imports: public import Init public meta import Init public import BusyBee.Common
#include <lean/lean.h>
#if defined(__clang__)
#pragma clang diagnostic ignored "-Wunused-parameter"
#pragma clang diagnostic ignored "-Wunused-label"
#elif defined(__GNUC__) && !defined(__CLANG__)
#pragma GCC diagnostic ignored "-Wunused-parameter"
#pragma GCC diagnostic ignored "-Wunused-label"
#pragma GCC diagnostic ignored "-Wunused-but-set-variable"
#endif
#ifdef __cplusplus
extern "C" {
#endif
lean_object* lean_nat_to_int(lean_object*);
uint8_t lean_int_dec_le(lean_object*, lean_object*);
lean_object* lean_int_mul(lean_object*, lean_object*);
uint8_t lean_int_dec_eq(lean_object*, lean_object*);
lean_object* lean_int_ediv(lean_object*, lean_object*);
lean_object* lean_int_add(lean_object*, lean_object*);
uint8_t lean_int_dec_lt(lean_object*, lean_object*);
static lean_once_cell_t lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__0_once = LEAN_ONCE_CELL_INITIALIZER;
static lean_object* lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__0;
static lean_once_cell_t lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__1_once = LEAN_ONCE_CELL_INITIALIZER;
static lean_object* lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__1;
static lean_once_cell_t lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__2_once = LEAN_ONCE_CELL_INITIALIZER;
static lean_object* lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__2;
static lean_once_cell_t lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__3_once = LEAN_ONCE_CELL_INITIALIZER;
static lean_object* lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__3;
static lean_once_cell_t lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__4_once = LEAN_ONCE_CELL_INITIALIZER;
static lean_object* lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__4;
static lean_once_cell_t lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__5_once = LEAN_ONCE_CELL_INITIALIZER;
static lean_object* lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__5;
static lean_once_cell_t lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__6_once = LEAN_ONCE_CELL_INITIALIZER;
static lean_object* lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__6;
static lean_once_cell_t lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__7_once = LEAN_ONCE_CELL_INITIALIZER;
static lean_object* lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__7;
static lean_once_cell_t lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__8_once = LEAN_ONCE_CELL_INITIALIZER;
static lean_object* lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__8;
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points(lean_object*, lean_object*);
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___boxed(lean_object*, lean_object*);
static lean_once_cell_t lp_BusyBee_BusyBee_Policy_DemoBank_interest__cover__points___closed__0_once = LEAN_ONCE_CELL_INITIALIZER;
static lean_object* lp_BusyBee_BusyBee_Policy_DemoBank_interest__cover__points___closed__0;
static lean_once_cell_t lp_BusyBee_BusyBee_Policy_DemoBank_interest__cover__points___closed__1_once = LEAN_ONCE_CELL_INITIALIZER;
static lean_object* lp_BusyBee_BusyBee_Policy_DemoBank_interest__cover__points___closed__1;
static lean_once_cell_t lp_BusyBee_BusyBee_Policy_DemoBank_interest__cover__points___closed__2_once = LEAN_ONCE_CELL_INITIALIZER;
static lean_object* lp_BusyBee_BusyBee_Policy_DemoBank_interest__cover__points___closed__2;
static lean_once_cell_t lp_BusyBee_BusyBee_Policy_DemoBank_interest__cover__points___closed__3_once = LEAN_ONCE_CELL_INITIALIZER;
static lean_object* lp_BusyBee_BusyBee_Policy_DemoBank_interest__cover__points___closed__3;
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_Policy_DemoBank_interest__cover__points(lean_object*, lean_object*);
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_Policy_DemoBank_interest__cover__points___boxed(lean_object*, lean_object*);
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_Policy_DemoBank_dscr__points(lean_object*, lean_object*);
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_Policy_DemoBank_dscr__points___boxed(lean_object*, lean_object*);
static lean_once_cell_t lp_BusyBee_BusyBee_Policy_DemoBank_current__ratio__points___closed__0_once = LEAN_ONCE_CELL_INITIALIZER;
static lean_object* lp_BusyBee_BusyBee_Policy_DemoBank_current__ratio__points___closed__0;
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_Policy_DemoBank_current__ratio__points(lean_object*, lean_object*);
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_Policy_DemoBank_current__ratio__points___boxed(lean_object*, lean_object*);
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_Policy_DemoBank_debt__equity__points(lean_object*, lean_object*);
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_Policy_DemoBank_debt__equity__points___boxed(lean_object*, lean_object*);
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_Policy_DemoBank_revenue__growth__points(lean_object*, lean_object*);
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_Policy_DemoBank_revenue__growth__points___boxed(lean_object*, lean_object*);
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_Policy_DemoBank_financial__strength__score(lean_object*, lean_object*, lean_object*, lean_object*, lean_object*, lean_object*, lean_object*, lean_object*, lean_object*, lean_object*, lean_object*);
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_Policy_DemoBank_financial__strength__score___boxed(lean_object*, lean_object*, lean_object*, lean_object*, lean_object*, lean_object*, lean_object*, lean_object*, lean_object*, lean_object*, lean_object*);
static lean_once_cell_t lp_BusyBee_BusyBee_Policy_DemoBank_financial__strength__score__grade___closed__0_once = LEAN_ONCE_CELL_INITIALIZER;
static lean_object* lp_BusyBee_BusyBee_Policy_DemoBank_financial__strength__score__grade___closed__0;
static lean_once_cell_t lp_BusyBee_BusyBee_Policy_DemoBank_financial__strength__score__grade___closed__1_once = LEAN_ONCE_CELL_INITIALIZER;
static lean_object* lp_BusyBee_BusyBee_Policy_DemoBank_financial__strength__score__grade___closed__1;
static lean_once_cell_t lp_BusyBee_BusyBee_Policy_DemoBank_financial__strength__score__grade___closed__2_once = LEAN_ONCE_CELL_INITIALIZER;
static lean_object* lp_BusyBee_BusyBee_Policy_DemoBank_financial__strength__score__grade___closed__2;
static const lean_string_object lp_BusyBee_BusyBee_Policy_DemoBank_financial__strength__score__grade___closed__3_value = {.m_header = {.m_rc = 0, .m_cs_sz = 0, .m_other = 0, .m_tag = 249}, .m_size = 5, .m_capacity = 5, .m_length = 4, .m_data = "Weak"};
static const lean_object* lp_BusyBee_BusyBee_Policy_DemoBank_financial__strength__score__grade___closed__3 = (const lean_object*)&lp_BusyBee_BusyBee_Policy_DemoBank_financial__strength__score__grade___closed__3_value;
static const lean_string_object lp_BusyBee_BusyBee_Policy_DemoBank_financial__strength__score__grade___closed__4_value = {.m_header = {.m_rc = 0, .m_cs_sz = 0, .m_other = 0, .m_tag = 249}, .m_size = 9, .m_capacity = 9, .m_length = 8, .m_data = "Moderate"};
static const lean_object* lp_BusyBee_BusyBee_Policy_DemoBank_financial__strength__score__grade___closed__4 = (const lean_object*)&lp_BusyBee_BusyBee_Policy_DemoBank_financial__strength__score__grade___closed__4_value;
static const lean_string_object lp_BusyBee_BusyBee_Policy_DemoBank_financial__strength__score__grade___closed__5_value = {.m_header = {.m_rc = 0, .m_cs_sz = 0, .m_other = 0, .m_tag = 249}, .m_size = 9, .m_capacity = 9, .m_length = 8, .m_data = "Adequate"};
static const lean_object* lp_BusyBee_BusyBee_Policy_DemoBank_financial__strength__score__grade___closed__5 = (const lean_object*)&lp_BusyBee_BusyBee_Policy_DemoBank_financial__strength__score__grade___closed__5_value;
static const lean_string_object lp_BusyBee_BusyBee_Policy_DemoBank_financial__strength__score__grade___closed__6_value = {.m_header = {.m_rc = 0, .m_cs_sz = 0, .m_other = 0, .m_tag = 249}, .m_size = 7, .m_capacity = 7, .m_length = 6, .m_data = "Strong"};
static const lean_object* lp_BusyBee_BusyBee_Policy_DemoBank_financial__strength__score__grade___closed__6 = (const lean_object*)&lp_BusyBee_BusyBee_Policy_DemoBank_financial__strength__score__grade___closed__6_value;
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_Policy_DemoBank_financial__strength__score__grade(lean_object*, lean_object*, lean_object*, lean_object*, lean_object*, lean_object*, lean_object*, lean_object*, lean_object*, lean_object*, lean_object*);
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_Policy_DemoBank_financial__strength__score__grade___boxed(lean_object*, lean_object*, lean_object*, lean_object*, lean_object*, lean_object*, lean_object*, lean_object*, lean_object*, lean_object*, lean_object*);
LEAN_EXPORT uint8_t lp_BusyBee_BusyBee_Policy_DemoBank_leverage__standard(lean_object*, lean_object*);
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_Policy_DemoBank_leverage__standard___boxed(lean_object*, lean_object*);
LEAN_EXPORT uint8_t lp_BusyBee_BusyBee_Policy_DemoBank_interest__cover__standard(lean_object*, lean_object*);
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_Policy_DemoBank_interest__cover__standard___boxed(lean_object*, lean_object*);
LEAN_EXPORT uint8_t lp_BusyBee_BusyBee_Policy_DemoBank_dscr__standard(lean_object*, lean_object*);
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_Policy_DemoBank_dscr__standard___boxed(lean_object*, lean_object*);
static lean_once_cell_t lp_BusyBee_BusyBee_Policy_DemoBank_base__grade___closed__0_once = LEAN_ONCE_CELL_INITIALIZER;
static lean_object* lp_BusyBee_BusyBee_Policy_DemoBank_base__grade___closed__0;
static lean_once_cell_t lp_BusyBee_BusyBee_Policy_DemoBank_base__grade___closed__1_once = LEAN_ONCE_CELL_INITIALIZER;
static lean_object* lp_BusyBee_BusyBee_Policy_DemoBank_base__grade___closed__1;
static lean_once_cell_t lp_BusyBee_BusyBee_Policy_DemoBank_base__grade___closed__2_once = LEAN_ONCE_CELL_INITIALIZER;
static lean_object* lp_BusyBee_BusyBee_Policy_DemoBank_base__grade___closed__2;
static lean_once_cell_t lp_BusyBee_BusyBee_Policy_DemoBank_base__grade___closed__3_once = LEAN_ONCE_CELL_INITIALIZER;
static lean_object* lp_BusyBee_BusyBee_Policy_DemoBank_base__grade___closed__3;
static lean_once_cell_t lp_BusyBee_BusyBee_Policy_DemoBank_base__grade___closed__4_once = LEAN_ONCE_CELL_INITIALIZER;
static lean_object* lp_BusyBee_BusyBee_Policy_DemoBank_base__grade___closed__4;
static lean_once_cell_t lp_BusyBee_BusyBee_Policy_DemoBank_base__grade___closed__5_once = LEAN_ONCE_CELL_INITIALIZER;
static lean_object* lp_BusyBee_BusyBee_Policy_DemoBank_base__grade___closed__5;
static lean_once_cell_t lp_BusyBee_BusyBee_Policy_DemoBank_base__grade___closed__6_once = LEAN_ONCE_CELL_INITIALIZER;
static lean_object* lp_BusyBee_BusyBee_Policy_DemoBank_base__grade___closed__6;
static lean_once_cell_t lp_BusyBee_BusyBee_Policy_DemoBank_base__grade___closed__7_once = LEAN_ONCE_CELL_INITIALIZER;
static lean_object* lp_BusyBee_BusyBee_Policy_DemoBank_base__grade___closed__7;
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_Policy_DemoBank_base__grade(lean_object*);
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_Policy_DemoBank_base__grade___boxed(lean_object*);
static lean_once_cell_t lp_BusyBee_BusyBee_Policy_DemoBank_rating__floor___closed__0_once = LEAN_ONCE_CELL_INITIALIZER;
static lean_object* lp_BusyBee_BusyBee_Policy_DemoBank_rating__floor___closed__0;
static lean_once_cell_t lp_BusyBee_BusyBee_Policy_DemoBank_rating__floor___closed__1_once = LEAN_ONCE_CELL_INITIALIZER;
static lean_object* lp_BusyBee_BusyBee_Policy_DemoBank_rating__floor___closed__1;
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_Policy_DemoBank_rating__floor(lean_object*);
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_Policy_DemoBank_rating__floor___boxed(lean_object*);
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_Policy_DemoBank_red__flag__notches(lean_object*);
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_Policy_DemoBank_red__flag__notches___boxed(lean_object*);
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_Policy_DemoBank_internal__risk__grade(lean_object*, lean_object*, lean_object*, lean_object*);
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_Policy_DemoBank_internal__risk__grade___boxed(lean_object*, lean_object*, lean_object*, lean_object*);
static const lean_string_object lp_BusyBee_BusyBee_Policy_DemoBank_internal__risk__grade__grade___closed__0_value = {.m_header = {.m_rc = 0, .m_cs_sz = 0, .m_other = 0, .m_tag = 249}, .m_size = 8, .m_capacity = 8, .m_length = 7, .m_data = "Decline"};
static const lean_object* lp_BusyBee_BusyBee_Policy_DemoBank_internal__risk__grade__grade___closed__0 = (const lean_object*)&lp_BusyBee_BusyBee_Policy_DemoBank_internal__risk__grade__grade___closed__0_value;
static const lean_string_object lp_BusyBee_BusyBee_Policy_DemoBank_internal__risk__grade__grade___closed__1_value = {.m_header = {.m_rc = 0, .m_cs_sz = 0, .m_other = 0, .m_tag = 249}, .m_size = 10, .m_capacity = 10, .m_length = 9, .m_data = "High risk"};
static const lean_object* lp_BusyBee_BusyBee_Policy_DemoBank_internal__risk__grade__grade___closed__1 = (const lean_object*)&lp_BusyBee_BusyBee_Policy_DemoBank_internal__risk__grade__grade___closed__1_value;
static const lean_string_object lp_BusyBee_BusyBee_Policy_DemoBank_internal__risk__grade__grade___closed__2_value = {.m_header = {.m_rc = 0, .m_cs_sz = 0, .m_other = 0, .m_tag = 249}, .m_size = 16, .m_capacity = 16, .m_length = 15, .m_data = "Acceptable risk"};
static const lean_object* lp_BusyBee_BusyBee_Policy_DemoBank_internal__risk__grade__grade___closed__2 = (const lean_object*)&lp_BusyBee_BusyBee_Policy_DemoBank_internal__risk__grade__grade___closed__2_value;
static const lean_string_object lp_BusyBee_BusyBee_Policy_DemoBank_internal__risk__grade__grade___closed__3_value = {.m_header = {.m_rc = 0, .m_cs_sz = 0, .m_other = 0, .m_tag = 249}, .m_size = 9, .m_capacity = 9, .m_length = 8, .m_data = "Low risk"};
static const lean_object* lp_BusyBee_BusyBee_Policy_DemoBank_internal__risk__grade__grade___closed__3 = (const lean_object*)&lp_BusyBee_BusyBee_Policy_DemoBank_internal__risk__grade__grade___closed__3_value;
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_Policy_DemoBank_internal__risk__grade__grade(lean_object*, lean_object*, lean_object*, lean_object*);
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_Policy_DemoBank_internal__risk__grade__grade___boxed(lean_object*, lean_object*, lean_object*, lean_object*);
static lean_once_cell_t lp_BusyBee_BusyBee_Policy_DemoBank_exposure__percentage___closed__0_once = LEAN_ONCE_CELL_INITIALIZER;
static lean_object* lp_BusyBee_BusyBee_Policy_DemoBank_exposure__percentage___closed__0;
static lean_once_cell_t lp_BusyBee_BusyBee_Policy_DemoBank_exposure__percentage___closed__1_once = LEAN_ONCE_CELL_INITIALIZER;
static lean_object* lp_BusyBee_BusyBee_Policy_DemoBank_exposure__percentage___closed__1;
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_Policy_DemoBank_exposure__percentage(lean_object*);
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_Policy_DemoBank_exposure__percentage___boxed(lean_object*);
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_Policy_DemoBank_capped__turnover__x4(lean_object*, lean_object*);
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_Policy_DemoBank_capped__turnover__x4___boxed(lean_object*, lean_object*);
static lean_once_cell_t lp_BusyBee_BusyBee_Policy_DemoBank_within__exposure__limit___closed__0_once = LEAN_ONCE_CELL_INITIALIZER;
static lean_object* lp_BusyBee_BusyBee_Policy_DemoBank_within__exposure__limit___closed__0;
LEAN_EXPORT uint8_t lp_BusyBee_BusyBee_Policy_DemoBank_within__exposure__limit(lean_object*, lean_object*, lean_object*, lean_object*, lean_object*);
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_Policy_DemoBank_within__exposure__limit___boxed(lean_object*, lean_object*, lean_object*, lean_object*, lean_object*);
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_Policy_DemoBank_maximum__exposure__test___redArg(lean_object*, lean_object*, lean_object*, lean_object*);
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_Policy_DemoBank_maximum__exposure__test___redArg___boxed(lean_object*, lean_object*, lean_object*, lean_object*);
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_Policy_DemoBank_maximum__exposure__test(lean_object*, lean_object*, lean_object*, lean_object*, lean_object*);
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_Policy_DemoBank_maximum__exposure__test___boxed(lean_object*, lean_object*, lean_object*, lean_object*, lean_object*);
static const lean_string_object lp_BusyBee_BusyBee_Policy_DemoBank_maximum__exposure__test__grade___closed__0_value = {.m_header = {.m_rc = 0, .m_cs_sz = 0, .m_other = 0, .m_tag = 249}, .m_size = 14, .m_capacity = 14, .m_length = 13, .m_data = "Exceeds limit"};
static const lean_object* lp_BusyBee_BusyBee_Policy_DemoBank_maximum__exposure__test__grade___closed__0 = (const lean_object*)&lp_BusyBee_BusyBee_Policy_DemoBank_maximum__exposure__test__grade___closed__0_value;
static const lean_string_object lp_BusyBee_BusyBee_Policy_DemoBank_maximum__exposure__test__grade___closed__1_value = {.m_header = {.m_rc = 0, .m_cs_sz = 0, .m_other = 0, .m_tag = 249}, .m_size = 13, .m_capacity = 13, .m_length = 12, .m_data = "Within limit"};
static const lean_object* lp_BusyBee_BusyBee_Policy_DemoBank_maximum__exposure__test__grade___closed__1 = (const lean_object*)&lp_BusyBee_BusyBee_Policy_DemoBank_maximum__exposure__test__grade___closed__1_value;
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_Policy_DemoBank_maximum__exposure__test__grade(lean_object*, lean_object*, lean_object*, lean_object*, lean_object*);
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_Policy_DemoBank_maximum__exposure__test__grade___boxed(lean_object*, lean_object*, lean_object*, lean_object*, lean_object*);
static lean_object* _init_lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__0(void){
_start:
{
lean_object* v___x_1_; lean_object* v___x_2_; 
v___x_1_ = lean_unsigned_to_nat(0u);
v___x_2_ = lean_nat_to_int(v___x_1_);
return v___x_2_;
}
}
static lean_object* _init_lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__1(void){
_start:
{
lean_object* v___x_3_; lean_object* v___x_4_; 
v___x_3_ = lean_unsigned_to_nat(2u);
v___x_4_ = lean_nat_to_int(v___x_3_);
return v___x_4_;
}
}
static lean_object* _init_lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__2(void){
_start:
{
lean_object* v___x_5_; lean_object* v___x_6_; 
v___x_5_ = lean_unsigned_to_nat(3u);
v___x_6_ = lean_nat_to_int(v___x_5_);
return v___x_6_;
}
}
static lean_object* _init_lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__3(void){
_start:
{
lean_object* v___x_7_; lean_object* v___x_8_; 
v___x_7_ = lean_unsigned_to_nat(5u);
v___x_8_ = lean_nat_to_int(v___x_7_);
return v___x_8_;
}
}
static lean_object* _init_lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__4(void){
_start:
{
lean_object* v___x_9_; lean_object* v___x_10_; 
v___x_9_ = lean_unsigned_to_nat(7u);
v___x_10_ = lean_nat_to_int(v___x_9_);
return v___x_10_;
}
}
static lean_object* _init_lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__5(void){
_start:
{
lean_object* v___x_11_; lean_object* v___x_12_; 
v___x_11_ = lean_unsigned_to_nat(9u);
v___x_12_ = lean_nat_to_int(v___x_11_);
return v___x_12_;
}
}
static lean_object* _init_lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__6(void){
_start:
{
lean_object* v___x_13_; lean_object* v___x_14_; 
v___x_13_ = lean_unsigned_to_nat(14u);
v___x_14_ = lean_nat_to_int(v___x_13_);
return v___x_14_;
}
}
static lean_object* _init_lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__7(void){
_start:
{
lean_object* v___x_15_; lean_object* v___x_16_; 
v___x_15_ = lean_unsigned_to_nat(20u);
v___x_16_ = lean_nat_to_int(v___x_15_);
return v___x_16_;
}
}
static lean_object* _init_lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__8(void){
_start:
{
lean_object* v___x_17_; lean_object* v___x_18_; 
v___x_17_ = lean_unsigned_to_nat(25u);
v___x_18_ = lean_nat_to_int(v___x_17_);
return v___x_18_;
}
}
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points(lean_object* v_net__debt_19_, lean_object* v_ebitda_20_){
_start:
{
lean_object* v___x_21_; uint8_t v___x_22_; 
v___x_21_ = lean_obj_once(&lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__0, &lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__0_once, _init_lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__0);
v___x_22_ = lean_int_dec_le(v_ebitda_20_, v___x_21_);
if (v___x_22_ == 0)
{
lean_object* v___x_23_; lean_object* v___x_24_; lean_object* v___x_25_; lean_object* v___x_26_; uint8_t v___x_27_; 
v___x_23_ = lean_obj_once(&lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__1, &lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__1_once, _init_lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__1);
v___x_24_ = lean_int_mul(v___x_23_, v_net__debt_19_);
v___x_25_ = lean_obj_once(&lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__2, &lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__2_once, _init_lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__2);
v___x_26_ = lean_int_mul(v___x_25_, v_ebitda_20_);
v___x_27_ = lean_int_dec_le(v___x_24_, v___x_26_);
lean_dec(v___x_26_);
if (v___x_27_ == 0)
{
lean_object* v___x_28_; lean_object* v___x_29_; uint8_t v___x_30_; 
v___x_28_ = lean_obj_once(&lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__3, &lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__3_once, _init_lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__3);
v___x_29_ = lean_int_mul(v___x_28_, v_ebitda_20_);
v___x_30_ = lean_int_dec_le(v___x_24_, v___x_29_);
lean_dec(v___x_29_);
if (v___x_30_ == 0)
{
lean_object* v___x_31_; lean_object* v___x_32_; uint8_t v___x_33_; 
v___x_31_ = lean_obj_once(&lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__4, &lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__4_once, _init_lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__4);
v___x_32_ = lean_int_mul(v___x_31_, v_ebitda_20_);
v___x_33_ = lean_int_dec_le(v___x_24_, v___x_32_);
lean_dec(v___x_32_);
if (v___x_33_ == 0)
{
lean_object* v___x_34_; lean_object* v___x_35_; uint8_t v___x_36_; 
v___x_34_ = lean_obj_once(&lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__5, &lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__5_once, _init_lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__5);
v___x_35_ = lean_int_mul(v___x_34_, v_ebitda_20_);
v___x_36_ = lean_int_dec_le(v___x_24_, v___x_35_);
lean_dec(v___x_35_);
lean_dec(v___x_24_);
if (v___x_36_ == 0)
{
return v___x_21_;
}
else
{
return v___x_31_;
}
}
else
{
lean_object* v___x_37_; 
lean_dec(v___x_24_);
v___x_37_ = lean_obj_once(&lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__6, &lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__6_once, _init_lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__6);
return v___x_37_;
}
}
else
{
lean_object* v___x_38_; 
lean_dec(v___x_24_);
v___x_38_ = lean_obj_once(&lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__7, &lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__7_once, _init_lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__7);
return v___x_38_;
}
}
else
{
lean_object* v___x_39_; 
lean_dec(v___x_24_);
v___x_39_ = lean_obj_once(&lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__8, &lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__8_once, _init_lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__8);
return v___x_39_;
}
}
else
{
return v___x_21_;
}
}
}
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___boxed(lean_object* v_net__debt_40_, lean_object* v_ebitda_41_){
_start:
{
lean_object* v_res_42_; 
v_res_42_ = lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points(v_net__debt_40_, v_ebitda_41_);
lean_dec(v_ebitda_41_);
lean_dec(v_net__debt_40_);
return v_res_42_;
}
}
static lean_object* _init_lp_BusyBee_BusyBee_Policy_DemoBank_interest__cover__points___closed__0(void){
_start:
{
lean_object* v___x_43_; lean_object* v___x_44_; 
v___x_43_ = lean_unsigned_to_nat(6u);
v___x_44_ = lean_nat_to_int(v___x_43_);
return v___x_44_;
}
}
static lean_object* _init_lp_BusyBee_BusyBee_Policy_DemoBank_interest__cover__points___closed__1(void){
_start:
{
lean_object* v___x_45_; lean_object* v___x_46_; 
v___x_45_ = lean_unsigned_to_nat(4u);
v___x_46_ = lean_nat_to_int(v___x_45_);
return v___x_46_;
}
}
static lean_object* _init_lp_BusyBee_BusyBee_Policy_DemoBank_interest__cover__points___closed__2(void){
_start:
{
lean_object* v___x_47_; lean_object* v___x_48_; 
v___x_47_ = lean_unsigned_to_nat(10u);
v___x_48_ = lean_nat_to_int(v___x_47_);
return v___x_48_;
}
}
static lean_object* _init_lp_BusyBee_BusyBee_Policy_DemoBank_interest__cover__points___closed__3(void){
_start:
{
lean_object* v___x_49_; lean_object* v___x_50_; 
v___x_49_ = lean_unsigned_to_nat(15u);
v___x_50_ = lean_nat_to_int(v___x_49_);
return v___x_50_;
}
}
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_Policy_DemoBank_interest__cover__points(lean_object* v_ebitda_51_, lean_object* v_interest__expense_52_){
_start:
{
lean_object* v___x_53_; uint8_t v___x_54_; 
v___x_53_ = lean_obj_once(&lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__0, &lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__0_once, _init_lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__0);
v___x_54_ = lean_int_dec_le(v_interest__expense_52_, v___x_53_);
if (v___x_54_ == 0)
{
lean_object* v___x_55_; lean_object* v___x_56_; uint8_t v___x_57_; 
v___x_55_ = lean_obj_once(&lp_BusyBee_BusyBee_Policy_DemoBank_interest__cover__points___closed__0, &lp_BusyBee_BusyBee_Policy_DemoBank_interest__cover__points___closed__0_once, _init_lp_BusyBee_BusyBee_Policy_DemoBank_interest__cover__points___closed__0);
v___x_56_ = lean_int_mul(v___x_55_, v_interest__expense_52_);
v___x_57_ = lean_int_dec_le(v___x_56_, v_ebitda_51_);
lean_dec(v___x_56_);
if (v___x_57_ == 0)
{
lean_object* v___x_58_; lean_object* v___x_59_; uint8_t v___x_60_; 
v___x_58_ = lean_obj_once(&lp_BusyBee_BusyBee_Policy_DemoBank_interest__cover__points___closed__1, &lp_BusyBee_BusyBee_Policy_DemoBank_interest__cover__points___closed__1_once, _init_lp_BusyBee_BusyBee_Policy_DemoBank_interest__cover__points___closed__1);
v___x_59_ = lean_int_mul(v___x_58_, v_interest__expense_52_);
v___x_60_ = lean_int_dec_le(v___x_59_, v_ebitda_51_);
lean_dec(v___x_59_);
if (v___x_60_ == 0)
{
lean_object* v___x_61_; lean_object* v___x_62_; lean_object* v___x_63_; lean_object* v___x_64_; uint8_t v___x_65_; 
v___x_61_ = lean_obj_once(&lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__3, &lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__3_once, _init_lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__3);
v___x_62_ = lean_int_mul(v___x_61_, v_interest__expense_52_);
v___x_63_ = lean_obj_once(&lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__1, &lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__1_once, _init_lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__1);
v___x_64_ = lean_int_mul(v___x_63_, v_ebitda_51_);
v___x_65_ = lean_int_dec_le(v___x_62_, v___x_64_);
lean_dec(v___x_62_);
if (v___x_65_ == 0)
{
lean_object* v___x_66_; lean_object* v___x_67_; uint8_t v___x_68_; 
v___x_66_ = lean_obj_once(&lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__2, &lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__2_once, _init_lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__2);
v___x_67_ = lean_int_mul(v___x_66_, v_interest__expense_52_);
v___x_68_ = lean_int_dec_le(v___x_67_, v___x_64_);
lean_dec(v___x_64_);
lean_dec(v___x_67_);
if (v___x_68_ == 0)
{
return v___x_53_;
}
else
{
return v___x_61_;
}
}
else
{
lean_object* v___x_69_; 
lean_dec(v___x_64_);
v___x_69_ = lean_obj_once(&lp_BusyBee_BusyBee_Policy_DemoBank_interest__cover__points___closed__2, &lp_BusyBee_BusyBee_Policy_DemoBank_interest__cover__points___closed__2_once, _init_lp_BusyBee_BusyBee_Policy_DemoBank_interest__cover__points___closed__2);
return v___x_69_;
}
}
else
{
lean_object* v___x_70_; 
v___x_70_ = lean_obj_once(&lp_BusyBee_BusyBee_Policy_DemoBank_interest__cover__points___closed__3, &lp_BusyBee_BusyBee_Policy_DemoBank_interest__cover__points___closed__3_once, _init_lp_BusyBee_BusyBee_Policy_DemoBank_interest__cover__points___closed__3);
return v___x_70_;
}
}
else
{
lean_object* v___x_71_; 
v___x_71_ = lean_obj_once(&lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__7, &lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__7_once, _init_lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__7);
return v___x_71_;
}
}
else
{
lean_object* v___x_72_; 
v___x_72_ = lean_obj_once(&lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__7, &lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__7_once, _init_lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__7);
return v___x_72_;
}
}
}
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_Policy_DemoBank_interest__cover__points___boxed(lean_object* v_ebitda_73_, lean_object* v_interest__expense_74_){
_start:
{
lean_object* v_res_75_; 
v_res_75_ = lp_BusyBee_BusyBee_Policy_DemoBank_interest__cover__points(v_ebitda_73_, v_interest__expense_74_);
lean_dec(v_interest__expense_74_);
lean_dec(v_ebitda_73_);
return v_res_75_;
}
}
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_Policy_DemoBank_dscr__points(lean_object* v_cfads_76_, lean_object* v_debt__service_77_){
_start:
{
lean_object* v___x_78_; uint8_t v___x_79_; 
v___x_78_ = lean_obj_once(&lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__0, &lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__0_once, _init_lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__0);
v___x_79_ = lean_int_dec_le(v_debt__service_77_, v___x_78_);
if (v___x_79_ == 0)
{
lean_object* v___x_80_; lean_object* v___x_81_; uint8_t v___x_82_; 
v___x_80_ = lean_obj_once(&lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__1, &lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__1_once, _init_lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__1);
v___x_81_ = lean_int_mul(v___x_80_, v_debt__service_77_);
v___x_82_ = lean_int_dec_le(v___x_81_, v_cfads_76_);
lean_dec(v___x_81_);
if (v___x_82_ == 0)
{
lean_object* v___x_83_; lean_object* v___x_84_; lean_object* v___x_85_; uint8_t v___x_86_; 
v___x_83_ = lean_obj_once(&lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__2, &lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__2_once, _init_lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__2);
v___x_84_ = lean_int_mul(v___x_83_, v_debt__service_77_);
v___x_85_ = lean_int_mul(v___x_80_, v_cfads_76_);
v___x_86_ = lean_int_dec_le(v___x_84_, v___x_85_);
lean_dec(v___x_85_);
lean_dec(v___x_84_);
if (v___x_86_ == 0)
{
lean_object* v___x_87_; lean_object* v___x_88_; lean_object* v___x_89_; lean_object* v___x_90_; uint8_t v___x_91_; 
v___x_87_ = lean_obj_once(&lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__3, &lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__3_once, _init_lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__3);
v___x_88_ = lean_int_mul(v___x_87_, v_debt__service_77_);
v___x_89_ = lean_obj_once(&lp_BusyBee_BusyBee_Policy_DemoBank_interest__cover__points___closed__1, &lp_BusyBee_BusyBee_Policy_DemoBank_interest__cover__points___closed__1_once, _init_lp_BusyBee_BusyBee_Policy_DemoBank_interest__cover__points___closed__1);
v___x_90_ = lean_int_mul(v___x_89_, v_cfads_76_);
v___x_91_ = lean_int_dec_le(v___x_88_, v___x_90_);
lean_dec(v___x_90_);
lean_dec(v___x_88_);
if (v___x_91_ == 0)
{
uint8_t v___x_92_; 
v___x_92_ = lean_int_dec_le(v_debt__service_77_, v_cfads_76_);
if (v___x_92_ == 0)
{
return v___x_78_;
}
else
{
return v___x_89_;
}
}
else
{
lean_object* v___x_93_; 
v___x_93_ = lean_obj_once(&lp_BusyBee_BusyBee_Policy_DemoBank_interest__cover__points___closed__2, &lp_BusyBee_BusyBee_Policy_DemoBank_interest__cover__points___closed__2_once, _init_lp_BusyBee_BusyBee_Policy_DemoBank_interest__cover__points___closed__2);
return v___x_93_;
}
}
else
{
lean_object* v___x_94_; 
v___x_94_ = lean_obj_once(&lp_BusyBee_BusyBee_Policy_DemoBank_interest__cover__points___closed__3, &lp_BusyBee_BusyBee_Policy_DemoBank_interest__cover__points___closed__3_once, _init_lp_BusyBee_BusyBee_Policy_DemoBank_interest__cover__points___closed__3);
return v___x_94_;
}
}
else
{
lean_object* v___x_95_; 
v___x_95_ = lean_obj_once(&lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__7, &lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__7_once, _init_lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__7);
return v___x_95_;
}
}
else
{
lean_object* v___x_96_; 
v___x_96_ = lean_obj_once(&lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__7, &lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__7_once, _init_lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__7);
return v___x_96_;
}
}
}
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_Policy_DemoBank_dscr__points___boxed(lean_object* v_cfads_97_, lean_object* v_debt__service_98_){
_start:
{
lean_object* v_res_99_; 
v_res_99_ = lp_BusyBee_BusyBee_Policy_DemoBank_dscr__points(v_cfads_97_, v_debt__service_98_);
lean_dec(v_debt__service_98_);
lean_dec(v_cfads_97_);
return v_res_99_;
}
}
static lean_object* _init_lp_BusyBee_BusyBee_Policy_DemoBank_current__ratio__points___closed__0(void){
_start:
{
lean_object* v___x_100_; lean_object* v___x_101_; 
v___x_100_ = lean_unsigned_to_nat(11u);
v___x_101_ = lean_nat_to_int(v___x_100_);
return v___x_101_;
}
}
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_Policy_DemoBank_current__ratio__points(lean_object* v_current__assets_102_, lean_object* v_current__liabilities_103_){
_start:
{
lean_object* v___x_104_; uint8_t v___x_105_; 
v___x_104_ = lean_obj_once(&lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__0, &lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__0_once, _init_lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__0);
v___x_105_ = lean_int_dec_le(v_current__liabilities_103_, v___x_104_);
if (v___x_105_ == 0)
{
lean_object* v___x_106_; lean_object* v___x_107_; lean_object* v___x_108_; lean_object* v___x_109_; uint8_t v___x_110_; 
v___x_106_ = lean_obj_once(&lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__2, &lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__2_once, _init_lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__2);
v___x_107_ = lean_int_mul(v___x_106_, v_current__liabilities_103_);
v___x_108_ = lean_obj_once(&lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__1, &lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__1_once, _init_lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__1);
v___x_109_ = lean_int_mul(v___x_108_, v_current__assets_102_);
v___x_110_ = lean_int_dec_le(v___x_107_, v___x_109_);
lean_dec(v___x_109_);
lean_dec(v___x_107_);
if (v___x_110_ == 0)
{
lean_object* v___x_111_; lean_object* v___x_112_; lean_object* v___x_113_; lean_object* v___x_114_; uint8_t v___x_115_; 
v___x_111_ = lean_obj_once(&lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__3, &lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__3_once, _init_lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__3);
v___x_112_ = lean_int_mul(v___x_111_, v_current__liabilities_103_);
v___x_113_ = lean_obj_once(&lp_BusyBee_BusyBee_Policy_DemoBank_interest__cover__points___closed__1, &lp_BusyBee_BusyBee_Policy_DemoBank_interest__cover__points___closed__1_once, _init_lp_BusyBee_BusyBee_Policy_DemoBank_interest__cover__points___closed__1);
v___x_114_ = lean_int_mul(v___x_113_, v_current__assets_102_);
v___x_115_ = lean_int_dec_le(v___x_112_, v___x_114_);
lean_dec(v___x_114_);
lean_dec(v___x_112_);
if (v___x_115_ == 0)
{
uint8_t v___x_116_; 
v___x_116_ = lean_int_dec_le(v_current__liabilities_103_, v_current__assets_102_);
if (v___x_116_ == 0)
{
return v___x_104_;
}
else
{
lean_object* v___x_117_; 
v___x_117_ = lean_obj_once(&lp_BusyBee_BusyBee_Policy_DemoBank_interest__cover__points___closed__0, &lp_BusyBee_BusyBee_Policy_DemoBank_interest__cover__points___closed__0_once, _init_lp_BusyBee_BusyBee_Policy_DemoBank_interest__cover__points___closed__0);
return v___x_117_;
}
}
else
{
lean_object* v___x_118_; 
v___x_118_ = lean_obj_once(&lp_BusyBee_BusyBee_Policy_DemoBank_current__ratio__points___closed__0, &lp_BusyBee_BusyBee_Policy_DemoBank_current__ratio__points___closed__0_once, _init_lp_BusyBee_BusyBee_Policy_DemoBank_current__ratio__points___closed__0);
return v___x_118_;
}
}
else
{
lean_object* v___x_119_; 
v___x_119_ = lean_obj_once(&lp_BusyBee_BusyBee_Policy_DemoBank_interest__cover__points___closed__3, &lp_BusyBee_BusyBee_Policy_DemoBank_interest__cover__points___closed__3_once, _init_lp_BusyBee_BusyBee_Policy_DemoBank_interest__cover__points___closed__3);
return v___x_119_;
}
}
else
{
return v___x_104_;
}
}
}
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_Policy_DemoBank_current__ratio__points___boxed(lean_object* v_current__assets_120_, lean_object* v_current__liabilities_121_){
_start:
{
lean_object* v_res_122_; 
v_res_122_ = lp_BusyBee_BusyBee_Policy_DemoBank_current__ratio__points(v_current__assets_120_, v_current__liabilities_121_);
lean_dec(v_current__liabilities_121_);
lean_dec(v_current__assets_120_);
return v_res_122_;
}
}
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_Policy_DemoBank_debt__equity__points(lean_object* v_total__debt_123_, lean_object* v_total__equity_124_){
_start:
{
lean_object* v___x_125_; uint8_t v___x_126_; 
v___x_125_ = lean_obj_once(&lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__0, &lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__0_once, _init_lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__0);
v___x_126_ = lean_int_dec_le(v_total__equity_124_, v___x_125_);
if (v___x_126_ == 0)
{
uint8_t v___x_127_; 
v___x_127_ = lean_int_dec_le(v_total__debt_123_, v_total__equity_124_);
if (v___x_127_ == 0)
{
lean_object* v___x_128_; lean_object* v___x_129_; uint8_t v___x_130_; 
v___x_128_ = lean_obj_once(&lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__1, &lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__1_once, _init_lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__1);
v___x_129_ = lean_int_mul(v___x_128_, v_total__equity_124_);
v___x_130_ = lean_int_dec_le(v_total__debt_123_, v___x_129_);
lean_dec(v___x_129_);
if (v___x_130_ == 0)
{
lean_object* v___x_131_; lean_object* v___x_132_; uint8_t v___x_133_; 
v___x_131_ = lean_obj_once(&lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__2, &lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__2_once, _init_lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__2);
v___x_132_ = lean_int_mul(v___x_131_, v_total__equity_124_);
v___x_133_ = lean_int_dec_le(v_total__debt_123_, v___x_132_);
lean_dec(v___x_132_);
if (v___x_133_ == 0)
{
return v___x_125_;
}
else
{
return v___x_131_;
}
}
else
{
lean_object* v___x_134_; 
v___x_134_ = lean_obj_once(&lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__4, &lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__4_once, _init_lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__4);
return v___x_134_;
}
}
else
{
lean_object* v___x_135_; 
v___x_135_ = lean_obj_once(&lp_BusyBee_BusyBee_Policy_DemoBank_interest__cover__points___closed__2, &lp_BusyBee_BusyBee_Policy_DemoBank_interest__cover__points___closed__2_once, _init_lp_BusyBee_BusyBee_Policy_DemoBank_interest__cover__points___closed__2);
return v___x_135_;
}
}
else
{
return v___x_125_;
}
}
}
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_Policy_DemoBank_debt__equity__points___boxed(lean_object* v_total__debt_136_, lean_object* v_total__equity_137_){
_start:
{
lean_object* v_res_138_; 
v_res_138_ = lp_BusyBee_BusyBee_Policy_DemoBank_debt__equity__points(v_total__debt_136_, v_total__equity_137_);
lean_dec(v_total__equity_137_);
lean_dec(v_total__debt_136_);
return v_res_138_;
}
}
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_Policy_DemoBank_revenue__growth__points(lean_object* v_revenue__current_139_, lean_object* v_revenue__previous_140_){
_start:
{
lean_object* v___x_141_; uint8_t v___x_142_; 
v___x_141_ = lean_obj_once(&lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__0, &lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__0_once, _init_lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__0);
v___x_142_ = lean_int_dec_le(v_revenue__previous_140_, v___x_141_);
if (v___x_142_ == 0)
{
lean_object* v___x_143_; lean_object* v___x_144_; lean_object* v___x_145_; lean_object* v___x_146_; uint8_t v___x_147_; 
v___x_143_ = lean_obj_once(&lp_BusyBee_BusyBee_Policy_DemoBank_current__ratio__points___closed__0, &lp_BusyBee_BusyBee_Policy_DemoBank_current__ratio__points___closed__0_once, _init_lp_BusyBee_BusyBee_Policy_DemoBank_current__ratio__points___closed__0);
v___x_144_ = lean_int_mul(v___x_143_, v_revenue__previous_140_);
v___x_145_ = lean_obj_once(&lp_BusyBee_BusyBee_Policy_DemoBank_interest__cover__points___closed__2, &lp_BusyBee_BusyBee_Policy_DemoBank_interest__cover__points___closed__2_once, _init_lp_BusyBee_BusyBee_Policy_DemoBank_interest__cover__points___closed__2);
v___x_146_ = lean_int_mul(v___x_145_, v_revenue__current_139_);
v___x_147_ = lean_int_dec_le(v___x_144_, v___x_146_);
lean_dec(v___x_144_);
if (v___x_147_ == 0)
{
uint8_t v___x_148_; 
v___x_148_ = lean_int_dec_le(v_revenue__previous_140_, v_revenue__current_139_);
if (v___x_148_ == 0)
{
lean_object* v___x_149_; lean_object* v___x_150_; uint8_t v___x_151_; 
v___x_149_ = lean_obj_once(&lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__5, &lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__5_once, _init_lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__5);
v___x_150_ = lean_int_mul(v___x_149_, v_revenue__previous_140_);
v___x_151_ = lean_int_dec_le(v___x_150_, v___x_146_);
lean_dec(v___x_146_);
lean_dec(v___x_150_);
if (v___x_151_ == 0)
{
return v___x_141_;
}
else
{
lean_object* v___x_152_; 
v___x_152_ = lean_obj_once(&lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__1, &lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__1_once, _init_lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__1);
return v___x_152_;
}
}
else
{
lean_object* v___x_153_; 
lean_dec(v___x_146_);
v___x_153_ = lean_obj_once(&lp_BusyBee_BusyBee_Policy_DemoBank_interest__cover__points___closed__0, &lp_BusyBee_BusyBee_Policy_DemoBank_interest__cover__points___closed__0_once, _init_lp_BusyBee_BusyBee_Policy_DemoBank_interest__cover__points___closed__0);
return v___x_153_;
}
}
else
{
lean_dec(v___x_146_);
return v___x_145_;
}
}
else
{
return v___x_141_;
}
}
}
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_Policy_DemoBank_revenue__growth__points___boxed(lean_object* v_revenue__current_154_, lean_object* v_revenue__previous_155_){
_start:
{
lean_object* v_res_156_; 
v_res_156_ = lp_BusyBee_BusyBee_Policy_DemoBank_revenue__growth__points(v_revenue__current_154_, v_revenue__previous_155_);
lean_dec(v_revenue__previous_155_);
lean_dec(v_revenue__current_154_);
return v_res_156_;
}
}
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_Policy_DemoBank_financial__strength__score(lean_object* v_net__debt_157_, lean_object* v_ebitda_158_, lean_object* v_interest__expense_159_, lean_object* v_cfads_160_, lean_object* v_debt__service_161_, lean_object* v_total__debt_162_, lean_object* v_total__equity_163_, lean_object* v_current__assets_164_, lean_object* v_current__liabilities_165_, lean_object* v_revenue__current_166_, lean_object* v_revenue__previous_167_){
_start:
{
lean_object* v___x_168_; lean_object* v___x_169_; lean_object* v___x_170_; lean_object* v___x_171_; lean_object* v___x_172_; lean_object* v___x_173_; lean_object* v___x_174_; lean_object* v___x_175_; lean_object* v___x_176_; lean_object* v___x_177_; lean_object* v___x_178_; 
v___x_168_ = lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points(v_net__debt_157_, v_ebitda_158_);
v___x_169_ = lp_BusyBee_BusyBee_Policy_DemoBank_interest__cover__points(v_ebitda_158_, v_interest__expense_159_);
v___x_170_ = lean_int_add(v___x_168_, v___x_169_);
lean_dec(v___x_169_);
lean_dec(v___x_168_);
v___x_171_ = lp_BusyBee_BusyBee_Policy_DemoBank_dscr__points(v_cfads_160_, v_debt__service_161_);
v___x_172_ = lean_int_add(v___x_170_, v___x_171_);
lean_dec(v___x_171_);
lean_dec(v___x_170_);
v___x_173_ = lp_BusyBee_BusyBee_Policy_DemoBank_current__ratio__points(v_current__assets_164_, v_current__liabilities_165_);
v___x_174_ = lean_int_add(v___x_172_, v___x_173_);
lean_dec(v___x_173_);
lean_dec(v___x_172_);
v___x_175_ = lp_BusyBee_BusyBee_Policy_DemoBank_debt__equity__points(v_total__debt_162_, v_total__equity_163_);
v___x_176_ = lean_int_add(v___x_174_, v___x_175_);
lean_dec(v___x_175_);
lean_dec(v___x_174_);
v___x_177_ = lp_BusyBee_BusyBee_Policy_DemoBank_revenue__growth__points(v_revenue__current_166_, v_revenue__previous_167_);
v___x_178_ = lean_int_add(v___x_176_, v___x_177_);
lean_dec(v___x_177_);
lean_dec(v___x_176_);
return v___x_178_;
}
}
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_Policy_DemoBank_financial__strength__score___boxed(lean_object* v_net__debt_179_, lean_object* v_ebitda_180_, lean_object* v_interest__expense_181_, lean_object* v_cfads_182_, lean_object* v_debt__service_183_, lean_object* v_total__debt_184_, lean_object* v_total__equity_185_, lean_object* v_current__assets_186_, lean_object* v_current__liabilities_187_, lean_object* v_revenue__current_188_, lean_object* v_revenue__previous_189_){
_start:
{
lean_object* v_res_190_; 
v_res_190_ = lp_BusyBee_BusyBee_Policy_DemoBank_financial__strength__score(v_net__debt_179_, v_ebitda_180_, v_interest__expense_181_, v_cfads_182_, v_debt__service_183_, v_total__debt_184_, v_total__equity_185_, v_current__assets_186_, v_current__liabilities_187_, v_revenue__current_188_, v_revenue__previous_189_);
lean_dec(v_revenue__previous_189_);
lean_dec(v_revenue__current_188_);
lean_dec(v_current__liabilities_187_);
lean_dec(v_current__assets_186_);
lean_dec(v_total__equity_185_);
lean_dec(v_total__debt_184_);
lean_dec(v_debt__service_183_);
lean_dec(v_cfads_182_);
lean_dec(v_interest__expense_181_);
lean_dec(v_ebitda_180_);
lean_dec(v_net__debt_179_);
return v_res_190_;
}
}
static lean_object* _init_lp_BusyBee_BusyBee_Policy_DemoBank_financial__strength__score__grade___closed__0(void){
_start:
{
lean_object* v___x_191_; lean_object* v___x_192_; 
v___x_191_ = lean_unsigned_to_nat(80u);
v___x_192_ = lean_nat_to_int(v___x_191_);
return v___x_192_;
}
}
static lean_object* _init_lp_BusyBee_BusyBee_Policy_DemoBank_financial__strength__score__grade___closed__1(void){
_start:
{
lean_object* v___x_193_; lean_object* v___x_194_; 
v___x_193_ = lean_unsigned_to_nat(60u);
v___x_194_ = lean_nat_to_int(v___x_193_);
return v___x_194_;
}
}
static lean_object* _init_lp_BusyBee_BusyBee_Policy_DemoBank_financial__strength__score__grade___closed__2(void){
_start:
{
lean_object* v___x_195_; lean_object* v___x_196_; 
v___x_195_ = lean_unsigned_to_nat(40u);
v___x_196_ = lean_nat_to_int(v___x_195_);
return v___x_196_;
}
}
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_Policy_DemoBank_financial__strength__score__grade(lean_object* v_net__debt_201_, lean_object* v_ebitda_202_, lean_object* v_interest__expense_203_, lean_object* v_cfads_204_, lean_object* v_debt__service_205_, lean_object* v_total__debt_206_, lean_object* v_total__equity_207_, lean_object* v_current__assets_208_, lean_object* v_current__liabilities_209_, lean_object* v_revenue__current_210_, lean_object* v_revenue__previous_211_){
_start:
{
lean_object* v_score_212_; lean_object* v___x_213_; uint8_t v___x_214_; 
v_score_212_ = lp_BusyBee_BusyBee_Policy_DemoBank_financial__strength__score(v_net__debt_201_, v_ebitda_202_, v_interest__expense_203_, v_cfads_204_, v_debt__service_205_, v_total__debt_206_, v_total__equity_207_, v_current__assets_208_, v_current__liabilities_209_, v_revenue__current_210_, v_revenue__previous_211_);
v___x_213_ = lean_obj_once(&lp_BusyBee_BusyBee_Policy_DemoBank_financial__strength__score__grade___closed__0, &lp_BusyBee_BusyBee_Policy_DemoBank_financial__strength__score__grade___closed__0_once, _init_lp_BusyBee_BusyBee_Policy_DemoBank_financial__strength__score__grade___closed__0);
v___x_214_ = lean_int_dec_le(v___x_213_, v_score_212_);
if (v___x_214_ == 0)
{
lean_object* v___x_215_; uint8_t v___x_216_; 
v___x_215_ = lean_obj_once(&lp_BusyBee_BusyBee_Policy_DemoBank_financial__strength__score__grade___closed__1, &lp_BusyBee_BusyBee_Policy_DemoBank_financial__strength__score__grade___closed__1_once, _init_lp_BusyBee_BusyBee_Policy_DemoBank_financial__strength__score__grade___closed__1);
v___x_216_ = lean_int_dec_le(v___x_215_, v_score_212_);
if (v___x_216_ == 0)
{
lean_object* v___x_217_; uint8_t v___x_218_; 
v___x_217_ = lean_obj_once(&lp_BusyBee_BusyBee_Policy_DemoBank_financial__strength__score__grade___closed__2, &lp_BusyBee_BusyBee_Policy_DemoBank_financial__strength__score__grade___closed__2_once, _init_lp_BusyBee_BusyBee_Policy_DemoBank_financial__strength__score__grade___closed__2);
v___x_218_ = lean_int_dec_le(v___x_217_, v_score_212_);
lean_dec(v_score_212_);
if (v___x_218_ == 0)
{
lean_object* v___x_219_; 
v___x_219_ = ((lean_object*)(lp_BusyBee_BusyBee_Policy_DemoBank_financial__strength__score__grade___closed__3));
return v___x_219_;
}
else
{
lean_object* v___x_220_; 
v___x_220_ = ((lean_object*)(lp_BusyBee_BusyBee_Policy_DemoBank_financial__strength__score__grade___closed__4));
return v___x_220_;
}
}
else
{
lean_object* v___x_221_; 
lean_dec(v_score_212_);
v___x_221_ = ((lean_object*)(lp_BusyBee_BusyBee_Policy_DemoBank_financial__strength__score__grade___closed__5));
return v___x_221_;
}
}
else
{
lean_object* v___x_222_; 
lean_dec(v_score_212_);
v___x_222_ = ((lean_object*)(lp_BusyBee_BusyBee_Policy_DemoBank_financial__strength__score__grade___closed__6));
return v___x_222_;
}
}
}
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_Policy_DemoBank_financial__strength__score__grade___boxed(lean_object* v_net__debt_223_, lean_object* v_ebitda_224_, lean_object* v_interest__expense_225_, lean_object* v_cfads_226_, lean_object* v_debt__service_227_, lean_object* v_total__debt_228_, lean_object* v_total__equity_229_, lean_object* v_current__assets_230_, lean_object* v_current__liabilities_231_, lean_object* v_revenue__current_232_, lean_object* v_revenue__previous_233_){
_start:
{
lean_object* v_res_234_; 
v_res_234_ = lp_BusyBee_BusyBee_Policy_DemoBank_financial__strength__score__grade(v_net__debt_223_, v_ebitda_224_, v_interest__expense_225_, v_cfads_226_, v_debt__service_227_, v_total__debt_228_, v_total__equity_229_, v_current__assets_230_, v_current__liabilities_231_, v_revenue__current_232_, v_revenue__previous_233_);
lean_dec(v_revenue__previous_233_);
lean_dec(v_revenue__current_232_);
lean_dec(v_current__liabilities_231_);
lean_dec(v_current__assets_230_);
lean_dec(v_total__equity_229_);
lean_dec(v_total__debt_228_);
lean_dec(v_debt__service_227_);
lean_dec(v_cfads_226_);
lean_dec(v_interest__expense_225_);
lean_dec(v_ebitda_224_);
lean_dec(v_net__debt_223_);
return v_res_234_;
}
}
LEAN_EXPORT uint8_t lp_BusyBee_BusyBee_Policy_DemoBank_leverage__standard(lean_object* v_net__debt_235_, lean_object* v_ebitda_236_){
_start:
{
lean_object* v___x_237_; uint8_t v___x_238_; 
v___x_237_ = lean_obj_once(&lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__0, &lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__0_once, _init_lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__0);
v___x_238_ = lean_int_dec_le(v_ebitda_236_, v___x_237_);
if (v___x_238_ == 0)
{
lean_object* v___x_239_; lean_object* v___x_240_; lean_object* v___x_241_; lean_object* v___x_242_; uint8_t v___x_243_; 
v___x_239_ = lean_obj_once(&lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__1, &lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__1_once, _init_lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__1);
v___x_240_ = lean_int_mul(v___x_239_, v_net__debt_235_);
v___x_241_ = lean_obj_once(&lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__4, &lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__4_once, _init_lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__4);
v___x_242_ = lean_int_mul(v___x_241_, v_ebitda_236_);
v___x_243_ = lean_int_dec_le(v___x_240_, v___x_242_);
lean_dec(v___x_242_);
if (v___x_243_ == 0)
{
lean_object* v___x_244_; lean_object* v___x_245_; uint8_t v___x_246_; 
v___x_244_ = lean_obj_once(&lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__5, &lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__5_once, _init_lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__5);
v___x_245_ = lean_int_mul(v___x_244_, v_ebitda_236_);
v___x_246_ = lean_int_dec_le(v___x_240_, v___x_245_);
lean_dec(v___x_245_);
lean_dec(v___x_240_);
if (v___x_246_ == 0)
{
uint8_t v___x_247_; 
v___x_247_ = 2;
return v___x_247_;
}
else
{
uint8_t v___x_248_; 
v___x_248_ = 1;
return v___x_248_;
}
}
else
{
uint8_t v___x_249_; 
lean_dec(v___x_240_);
v___x_249_ = 0;
return v___x_249_;
}
}
else
{
uint8_t v___x_250_; 
v___x_250_ = 2;
return v___x_250_;
}
}
}
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_Policy_DemoBank_leverage__standard___boxed(lean_object* v_net__debt_251_, lean_object* v_ebitda_252_){
_start:
{
uint8_t v_res_253_; lean_object* v_r_254_; 
v_res_253_ = lp_BusyBee_BusyBee_Policy_DemoBank_leverage__standard(v_net__debt_251_, v_ebitda_252_);
lean_dec(v_ebitda_252_);
lean_dec(v_net__debt_251_);
v_r_254_ = lean_box(v_res_253_);
return v_r_254_;
}
}
LEAN_EXPORT uint8_t lp_BusyBee_BusyBee_Policy_DemoBank_interest__cover__standard(lean_object* v_ebitda_255_, lean_object* v_interest__expense_256_){
_start:
{
lean_object* v___x_257_; uint8_t v___x_258_; 
v___x_257_ = lean_obj_once(&lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__0, &lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__0_once, _init_lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__0);
v___x_258_ = lean_int_dec_le(v_interest__expense_256_, v___x_257_);
if (v___x_258_ == 0)
{
lean_object* v___x_259_; lean_object* v___x_260_; uint8_t v___x_261_; 
v___x_259_ = lean_obj_once(&lp_BusyBee_BusyBee_Policy_DemoBank_interest__cover__points___closed__1, &lp_BusyBee_BusyBee_Policy_DemoBank_interest__cover__points___closed__1_once, _init_lp_BusyBee_BusyBee_Policy_DemoBank_interest__cover__points___closed__1);
v___x_260_ = lean_int_mul(v___x_259_, v_interest__expense_256_);
v___x_261_ = lean_int_dec_le(v___x_260_, v_ebitda_255_);
lean_dec(v___x_260_);
if (v___x_261_ == 0)
{
lean_object* v___x_262_; lean_object* v___x_263_; lean_object* v___x_264_; lean_object* v___x_265_; uint8_t v___x_266_; 
v___x_262_ = lean_obj_once(&lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__3, &lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__3_once, _init_lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__3);
v___x_263_ = lean_int_mul(v___x_262_, v_interest__expense_256_);
v___x_264_ = lean_obj_once(&lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__1, &lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__1_once, _init_lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__1);
v___x_265_ = lean_int_mul(v___x_264_, v_ebitda_255_);
v___x_266_ = lean_int_dec_le(v___x_263_, v___x_265_);
lean_dec(v___x_265_);
lean_dec(v___x_263_);
if (v___x_266_ == 0)
{
uint8_t v___x_267_; 
v___x_267_ = 2;
return v___x_267_;
}
else
{
uint8_t v___x_268_; 
v___x_268_ = 1;
return v___x_268_;
}
}
else
{
uint8_t v___x_269_; 
v___x_269_ = 0;
return v___x_269_;
}
}
else
{
uint8_t v___x_270_; 
v___x_270_ = 0;
return v___x_270_;
}
}
}
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_Policy_DemoBank_interest__cover__standard___boxed(lean_object* v_ebitda_271_, lean_object* v_interest__expense_272_){
_start:
{
uint8_t v_res_273_; lean_object* v_r_274_; 
v_res_273_ = lp_BusyBee_BusyBee_Policy_DemoBank_interest__cover__standard(v_ebitda_271_, v_interest__expense_272_);
lean_dec(v_interest__expense_272_);
lean_dec(v_ebitda_271_);
v_r_274_ = lean_box(v_res_273_);
return v_r_274_;
}
}
LEAN_EXPORT uint8_t lp_BusyBee_BusyBee_Policy_DemoBank_dscr__standard(lean_object* v_cfads_275_, lean_object* v_debt__service_276_){
_start:
{
lean_object* v___x_277_; uint8_t v___x_278_; 
v___x_277_ = lean_obj_once(&lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__0, &lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__0_once, _init_lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__0);
v___x_278_ = lean_int_dec_le(v_debt__service_276_, v___x_277_);
if (v___x_278_ == 0)
{
lean_object* v___x_279_; lean_object* v___x_280_; lean_object* v___x_281_; lean_object* v___x_282_; uint8_t v___x_283_; 
v___x_279_ = lean_obj_once(&lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__2, &lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__2_once, _init_lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__2);
v___x_280_ = lean_int_mul(v___x_279_, v_debt__service_276_);
v___x_281_ = lean_obj_once(&lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__1, &lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__1_once, _init_lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__1);
v___x_282_ = lean_int_mul(v___x_281_, v_cfads_275_);
v___x_283_ = lean_int_dec_le(v___x_280_, v___x_282_);
lean_dec(v___x_282_);
lean_dec(v___x_280_);
if (v___x_283_ == 0)
{
lean_object* v___x_284_; lean_object* v___x_285_; lean_object* v___x_286_; lean_object* v___x_287_; uint8_t v___x_288_; 
v___x_284_ = lean_obj_once(&lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__3, &lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__3_once, _init_lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__3);
v___x_285_ = lean_int_mul(v___x_284_, v_debt__service_276_);
v___x_286_ = lean_obj_once(&lp_BusyBee_BusyBee_Policy_DemoBank_interest__cover__points___closed__1, &lp_BusyBee_BusyBee_Policy_DemoBank_interest__cover__points___closed__1_once, _init_lp_BusyBee_BusyBee_Policy_DemoBank_interest__cover__points___closed__1);
v___x_287_ = lean_int_mul(v___x_286_, v_cfads_275_);
v___x_288_ = lean_int_dec_le(v___x_285_, v___x_287_);
lean_dec(v___x_287_);
lean_dec(v___x_285_);
if (v___x_288_ == 0)
{
uint8_t v___x_289_; 
v___x_289_ = 2;
return v___x_289_;
}
else
{
uint8_t v___x_290_; 
v___x_290_ = 1;
return v___x_290_;
}
}
else
{
uint8_t v___x_291_; 
v___x_291_ = 0;
return v___x_291_;
}
}
else
{
uint8_t v___x_292_; 
v___x_292_ = 0;
return v___x_292_;
}
}
}
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_Policy_DemoBank_dscr__standard___boxed(lean_object* v_cfads_293_, lean_object* v_debt__service_294_){
_start:
{
uint8_t v_res_295_; lean_object* v_r_296_; 
v_res_295_ = lp_BusyBee_BusyBee_Policy_DemoBank_dscr__standard(v_cfads_293_, v_debt__service_294_);
lean_dec(v_debt__service_294_);
lean_dec(v_cfads_293_);
v_r_296_ = lean_box(v_res_295_);
return v_r_296_;
}
}
static lean_object* _init_lp_BusyBee_BusyBee_Policy_DemoBank_base__grade___closed__0(void){
_start:
{
lean_object* v___x_297_; lean_object* v___x_298_; 
v___x_297_ = lean_unsigned_to_nat(85u);
v___x_298_ = lean_nat_to_int(v___x_297_);
return v___x_298_;
}
}
static lean_object* _init_lp_BusyBee_BusyBee_Policy_DemoBank_base__grade___closed__1(void){
_start:
{
lean_object* v___x_299_; lean_object* v___x_300_; 
v___x_299_ = lean_unsigned_to_nat(75u);
v___x_300_ = lean_nat_to_int(v___x_299_);
return v___x_300_;
}
}
static lean_object* _init_lp_BusyBee_BusyBee_Policy_DemoBank_base__grade___closed__2(void){
_start:
{
lean_object* v___x_301_; lean_object* v___x_302_; 
v___x_301_ = lean_unsigned_to_nat(65u);
v___x_302_ = lean_nat_to_int(v___x_301_);
return v___x_302_;
}
}
static lean_object* _init_lp_BusyBee_BusyBee_Policy_DemoBank_base__grade___closed__3(void){
_start:
{
lean_object* v___x_303_; lean_object* v___x_304_; 
v___x_303_ = lean_unsigned_to_nat(55u);
v___x_304_ = lean_nat_to_int(v___x_303_);
return v___x_304_;
}
}
static lean_object* _init_lp_BusyBee_BusyBee_Policy_DemoBank_base__grade___closed__4(void){
_start:
{
lean_object* v___x_305_; lean_object* v___x_306_; 
v___x_305_ = lean_unsigned_to_nat(45u);
v___x_306_ = lean_nat_to_int(v___x_305_);
return v___x_306_;
}
}
static lean_object* _init_lp_BusyBee_BusyBee_Policy_DemoBank_base__grade___closed__5(void){
_start:
{
lean_object* v___x_307_; lean_object* v___x_308_; 
v___x_307_ = lean_unsigned_to_nat(35u);
v___x_308_ = lean_nat_to_int(v___x_307_);
return v___x_308_;
}
}
static lean_object* _init_lp_BusyBee_BusyBee_Policy_DemoBank_base__grade___closed__6(void){
_start:
{
lean_object* v___x_309_; lean_object* v___x_310_; 
v___x_309_ = lean_unsigned_to_nat(8u);
v___x_310_ = lean_nat_to_int(v___x_309_);
return v___x_310_;
}
}
static lean_object* _init_lp_BusyBee_BusyBee_Policy_DemoBank_base__grade___closed__7(void){
_start:
{
lean_object* v___x_311_; lean_object* v___x_312_; 
v___x_311_ = lean_unsigned_to_nat(1u);
v___x_312_ = lean_nat_to_int(v___x_311_);
return v___x_312_;
}
}
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_Policy_DemoBank_base__grade(lean_object* v_fss_313_){
_start:
{
lean_object* v___x_314_; uint8_t v___x_315_; 
v___x_314_ = lean_obj_once(&lp_BusyBee_BusyBee_Policy_DemoBank_base__grade___closed__0, &lp_BusyBee_BusyBee_Policy_DemoBank_base__grade___closed__0_once, _init_lp_BusyBee_BusyBee_Policy_DemoBank_base__grade___closed__0);
v___x_315_ = lean_int_dec_le(v___x_314_, v_fss_313_);
if (v___x_315_ == 0)
{
lean_object* v___x_316_; uint8_t v___x_317_; 
v___x_316_ = lean_obj_once(&lp_BusyBee_BusyBee_Policy_DemoBank_base__grade___closed__1, &lp_BusyBee_BusyBee_Policy_DemoBank_base__grade___closed__1_once, _init_lp_BusyBee_BusyBee_Policy_DemoBank_base__grade___closed__1);
v___x_317_ = lean_int_dec_le(v___x_316_, v_fss_313_);
if (v___x_317_ == 0)
{
lean_object* v___x_318_; uint8_t v___x_319_; 
v___x_318_ = lean_obj_once(&lp_BusyBee_BusyBee_Policy_DemoBank_base__grade___closed__2, &lp_BusyBee_BusyBee_Policy_DemoBank_base__grade___closed__2_once, _init_lp_BusyBee_BusyBee_Policy_DemoBank_base__grade___closed__2);
v___x_319_ = lean_int_dec_le(v___x_318_, v_fss_313_);
if (v___x_319_ == 0)
{
lean_object* v___x_320_; uint8_t v___x_321_; 
v___x_320_ = lean_obj_once(&lp_BusyBee_BusyBee_Policy_DemoBank_base__grade___closed__3, &lp_BusyBee_BusyBee_Policy_DemoBank_base__grade___closed__3_once, _init_lp_BusyBee_BusyBee_Policy_DemoBank_base__grade___closed__3);
v___x_321_ = lean_int_dec_le(v___x_320_, v_fss_313_);
if (v___x_321_ == 0)
{
lean_object* v___x_322_; uint8_t v___x_323_; 
v___x_322_ = lean_obj_once(&lp_BusyBee_BusyBee_Policy_DemoBank_base__grade___closed__4, &lp_BusyBee_BusyBee_Policy_DemoBank_base__grade___closed__4_once, _init_lp_BusyBee_BusyBee_Policy_DemoBank_base__grade___closed__4);
v___x_323_ = lean_int_dec_le(v___x_322_, v_fss_313_);
if (v___x_323_ == 0)
{
lean_object* v___x_324_; uint8_t v___x_325_; 
v___x_324_ = lean_obj_once(&lp_BusyBee_BusyBee_Policy_DemoBank_base__grade___closed__5, &lp_BusyBee_BusyBee_Policy_DemoBank_base__grade___closed__5_once, _init_lp_BusyBee_BusyBee_Policy_DemoBank_base__grade___closed__5);
v___x_325_ = lean_int_dec_le(v___x_324_, v_fss_313_);
if (v___x_325_ == 0)
{
lean_object* v___x_326_; uint8_t v___x_327_; 
v___x_326_ = lean_obj_once(&lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__8, &lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__8_once, _init_lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__8);
v___x_327_ = lean_int_dec_le(v___x_326_, v_fss_313_);
if (v___x_327_ == 0)
{
lean_object* v___x_328_; 
v___x_328_ = lean_obj_once(&lp_BusyBee_BusyBee_Policy_DemoBank_base__grade___closed__6, &lp_BusyBee_BusyBee_Policy_DemoBank_base__grade___closed__6_once, _init_lp_BusyBee_BusyBee_Policy_DemoBank_base__grade___closed__6);
return v___x_328_;
}
else
{
lean_object* v___x_329_; 
v___x_329_ = lean_obj_once(&lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__4, &lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__4_once, _init_lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__4);
return v___x_329_;
}
}
else
{
lean_object* v___x_330_; 
v___x_330_ = lean_obj_once(&lp_BusyBee_BusyBee_Policy_DemoBank_interest__cover__points___closed__0, &lp_BusyBee_BusyBee_Policy_DemoBank_interest__cover__points___closed__0_once, _init_lp_BusyBee_BusyBee_Policy_DemoBank_interest__cover__points___closed__0);
return v___x_330_;
}
}
else
{
lean_object* v___x_331_; 
v___x_331_ = lean_obj_once(&lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__3, &lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__3_once, _init_lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__3);
return v___x_331_;
}
}
else
{
lean_object* v___x_332_; 
v___x_332_ = lean_obj_once(&lp_BusyBee_BusyBee_Policy_DemoBank_interest__cover__points___closed__1, &lp_BusyBee_BusyBee_Policy_DemoBank_interest__cover__points___closed__1_once, _init_lp_BusyBee_BusyBee_Policy_DemoBank_interest__cover__points___closed__1);
return v___x_332_;
}
}
else
{
lean_object* v___x_333_; 
v___x_333_ = lean_obj_once(&lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__2, &lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__2_once, _init_lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__2);
return v___x_333_;
}
}
else
{
lean_object* v___x_334_; 
v___x_334_ = lean_obj_once(&lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__1, &lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__1_once, _init_lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__1);
return v___x_334_;
}
}
else
{
lean_object* v___x_335_; 
v___x_335_ = lean_obj_once(&lp_BusyBee_BusyBee_Policy_DemoBank_base__grade___closed__7, &lp_BusyBee_BusyBee_Policy_DemoBank_base__grade___closed__7_once, _init_lp_BusyBee_BusyBee_Policy_DemoBank_base__grade___closed__7);
return v___x_335_;
}
}
}
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_Policy_DemoBank_base__grade___boxed(lean_object* v_fss_336_){
_start:
{
lean_object* v_res_337_; 
v_res_337_ = lp_BusyBee_BusyBee_Policy_DemoBank_base__grade(v_fss_336_);
lean_dec(v_fss_336_);
return v_res_337_;
}
}
static lean_object* _init_lp_BusyBee_BusyBee_Policy_DemoBank_rating__floor___closed__0(void){
_start:
{
lean_object* v___x_338_; lean_object* v___x_339_; 
v___x_338_ = lean_unsigned_to_nat(13u);
v___x_339_ = lean_nat_to_int(v___x_338_);
return v___x_339_;
}
}
static lean_object* _init_lp_BusyBee_BusyBee_Policy_DemoBank_rating__floor___closed__1(void){
_start:
{
lean_object* v___x_340_; lean_object* v___x_341_; 
v___x_340_ = lean_unsigned_to_nat(16u);
v___x_341_ = lean_nat_to_int(v___x_340_);
return v___x_341_;
}
}
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_Policy_DemoBank_rating__floor(lean_object* v_external__rating__index_342_){
_start:
{
lean_object* v___x_343_; uint8_t v___x_344_; 
v___x_343_ = lean_obj_once(&lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__2, &lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__2_once, _init_lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__2);
v___x_344_ = lean_int_dec_le(v_external__rating__index_342_, v___x_343_);
if (v___x_344_ == 0)
{
lean_object* v___x_345_; uint8_t v___x_346_; 
v___x_345_ = lean_obj_once(&lp_BusyBee_BusyBee_Policy_DemoBank_interest__cover__points___closed__0, &lp_BusyBee_BusyBee_Policy_DemoBank_interest__cover__points___closed__0_once, _init_lp_BusyBee_BusyBee_Policy_DemoBank_interest__cover__points___closed__0);
v___x_346_ = lean_int_dec_le(v_external__rating__index_342_, v___x_345_);
if (v___x_346_ == 0)
{
lean_object* v___x_347_; uint8_t v___x_348_; 
v___x_347_ = lean_obj_once(&lp_BusyBee_BusyBee_Policy_DemoBank_base__grade___closed__6, &lp_BusyBee_BusyBee_Policy_DemoBank_base__grade___closed__6_once, _init_lp_BusyBee_BusyBee_Policy_DemoBank_base__grade___closed__6);
v___x_348_ = lean_int_dec_le(v_external__rating__index_342_, v___x_347_);
if (v___x_348_ == 0)
{
lean_object* v___x_349_; uint8_t v___x_350_; 
v___x_349_ = lean_obj_once(&lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__5, &lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__5_once, _init_lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__5);
v___x_350_ = lean_int_dec_eq(v_external__rating__index_342_, v___x_349_);
if (v___x_350_ == 0)
{
lean_object* v___x_351_; uint8_t v___x_352_; 
v___x_351_ = lean_obj_once(&lp_BusyBee_BusyBee_Policy_DemoBank_interest__cover__points___closed__2, &lp_BusyBee_BusyBee_Policy_DemoBank_interest__cover__points___closed__2_once, _init_lp_BusyBee_BusyBee_Policy_DemoBank_interest__cover__points___closed__2);
v___x_352_ = lean_int_dec_eq(v_external__rating__index_342_, v___x_351_);
if (v___x_352_ == 0)
{
lean_object* v___x_353_; uint8_t v___x_354_; 
v___x_353_ = lean_obj_once(&lp_BusyBee_BusyBee_Policy_DemoBank_rating__floor___closed__0, &lp_BusyBee_BusyBee_Policy_DemoBank_rating__floor___closed__0_once, _init_lp_BusyBee_BusyBee_Policy_DemoBank_rating__floor___closed__0);
v___x_354_ = lean_int_dec_le(v_external__rating__index_342_, v___x_353_);
if (v___x_354_ == 0)
{
lean_object* v___x_355_; uint8_t v___x_356_; 
v___x_355_ = lean_obj_once(&lp_BusyBee_BusyBee_Policy_DemoBank_rating__floor___closed__1, &lp_BusyBee_BusyBee_Policy_DemoBank_rating__floor___closed__1_once, _init_lp_BusyBee_BusyBee_Policy_DemoBank_rating__floor___closed__1);
v___x_356_ = lean_int_dec_le(v_external__rating__index_342_, v___x_355_);
if (v___x_356_ == 0)
{
return v___x_347_;
}
else
{
lean_object* v___x_357_; 
v___x_357_ = lean_obj_once(&lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__4, &lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__4_once, _init_lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__4);
return v___x_357_;
}
}
else
{
return v___x_345_;
}
}
else
{
lean_object* v___x_358_; 
v___x_358_ = lean_obj_once(&lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__3, &lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__3_once, _init_lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__3);
return v___x_358_;
}
}
else
{
lean_object* v___x_359_; 
v___x_359_ = lean_obj_once(&lp_BusyBee_BusyBee_Policy_DemoBank_interest__cover__points___closed__1, &lp_BusyBee_BusyBee_Policy_DemoBank_interest__cover__points___closed__1_once, _init_lp_BusyBee_BusyBee_Policy_DemoBank_interest__cover__points___closed__1);
return v___x_359_;
}
}
else
{
return v___x_343_;
}
}
else
{
lean_object* v___x_360_; 
v___x_360_ = lean_obj_once(&lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__1, &lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__1_once, _init_lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__1);
return v___x_360_;
}
}
else
{
lean_object* v___x_361_; 
v___x_361_ = lean_obj_once(&lp_BusyBee_BusyBee_Policy_DemoBank_base__grade___closed__7, &lp_BusyBee_BusyBee_Policy_DemoBank_base__grade___closed__7_once, _init_lp_BusyBee_BusyBee_Policy_DemoBank_base__grade___closed__7);
return v___x_361_;
}
}
}
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_Policy_DemoBank_rating__floor___boxed(lean_object* v_external__rating__index_362_){
_start:
{
lean_object* v_res_363_; 
v_res_363_ = lp_BusyBee_BusyBee_Policy_DemoBank_rating__floor(v_external__rating__index_362_);
lean_dec(v_external__rating__index_362_);
return v_res_363_;
}
}
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_Policy_DemoBank_red__flag__notches(lean_object* v_major__red__flag__count_364_){
_start:
{
lean_object* v___x_365_; uint8_t v___x_366_; 
v___x_365_ = lean_obj_once(&lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__0, &lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__0_once, _init_lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__0);
v___x_366_ = lean_int_dec_le(v_major__red__flag__count_364_, v___x_365_);
if (v___x_366_ == 0)
{
lean_object* v___x_367_; uint8_t v___x_368_; 
v___x_367_ = lean_obj_once(&lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__2, &lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__2_once, _init_lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__2);
v___x_368_ = lean_int_dec_le(v_major__red__flag__count_364_, v___x_367_);
if (v___x_368_ == 0)
{
return v___x_367_;
}
else
{
lean_inc(v_major__red__flag__count_364_);
return v_major__red__flag__count_364_;
}
}
else
{
return v___x_365_;
}
}
}
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_Policy_DemoBank_red__flag__notches___boxed(lean_object* v_major__red__flag__count_369_){
_start:
{
lean_object* v_res_370_; 
v_res_370_ = lp_BusyBee_BusyBee_Policy_DemoBank_red__flag__notches(v_major__red__flag__count_369_);
lean_dec(v_major__red__flag__count_369_);
return v_res_370_;
}
}
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_Policy_DemoBank_internal__risk__grade(lean_object* v_financial__strength__score_371_, lean_object* v_external__rating__index_372_, lean_object* v_major__red__flag__count_373_, lean_object* v_default__flag_374_){
_start:
{
lean_object* v___y_376_; lean_object* v___x_384_; lean_object* v___x_385_; uint8_t v___x_386_; 
v___x_384_ = lp_BusyBee_BusyBee_Policy_DemoBank_base__grade(v_financial__strength__score_371_);
v___x_385_ = lp_BusyBee_BusyBee_Policy_DemoBank_rating__floor(v_external__rating__index_372_);
v___x_386_ = lean_int_dec_le(v___x_384_, v___x_385_);
if (v___x_386_ == 0)
{
lean_dec(v___x_385_);
v___y_376_ = v___x_384_;
goto v___jp_375_;
}
else
{
lean_dec(v___x_384_);
v___y_376_ = v___x_385_;
goto v___jp_375_;
}
v___jp_375_:
{
lean_object* v___x_377_; uint8_t v___x_378_; 
v___x_377_ = lean_obj_once(&lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__0, &lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__0_once, _init_lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__0);
v___x_378_ = lean_int_dec_lt(v___x_377_, v_default__flag_374_);
if (v___x_378_ == 0)
{
lean_object* v___x_379_; lean_object* v_notched_380_; lean_object* v___x_381_; uint8_t v___x_382_; 
v___x_379_ = lp_BusyBee_BusyBee_Policy_DemoBank_red__flag__notches(v_major__red__flag__count_373_);
v_notched_380_ = lean_int_add(v___y_376_, v___x_379_);
lean_dec(v___x_379_);
lean_dec(v___y_376_);
v___x_381_ = lean_obj_once(&lp_BusyBee_BusyBee_Policy_DemoBank_base__grade___closed__6, &lp_BusyBee_BusyBee_Policy_DemoBank_base__grade___closed__6_once, _init_lp_BusyBee_BusyBee_Policy_DemoBank_base__grade___closed__6);
v___x_382_ = lean_int_dec_le(v___x_381_, v_notched_380_);
if (v___x_382_ == 0)
{
return v_notched_380_;
}
else
{
lean_dec(v_notched_380_);
return v___x_381_;
}
}
else
{
lean_object* v___x_383_; 
lean_dec(v___y_376_);
v___x_383_ = lean_obj_once(&lp_BusyBee_BusyBee_Policy_DemoBank_base__grade___closed__6, &lp_BusyBee_BusyBee_Policy_DemoBank_base__grade___closed__6_once, _init_lp_BusyBee_BusyBee_Policy_DemoBank_base__grade___closed__6);
return v___x_383_;
}
}
}
}
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_Policy_DemoBank_internal__risk__grade___boxed(lean_object* v_financial__strength__score_387_, lean_object* v_external__rating__index_388_, lean_object* v_major__red__flag__count_389_, lean_object* v_default__flag_390_){
_start:
{
lean_object* v_res_391_; 
v_res_391_ = lp_BusyBee_BusyBee_Policy_DemoBank_internal__risk__grade(v_financial__strength__score_387_, v_external__rating__index_388_, v_major__red__flag__count_389_, v_default__flag_390_);
lean_dec(v_default__flag_390_);
lean_dec(v_major__red__flag__count_389_);
lean_dec(v_external__rating__index_388_);
lean_dec(v_financial__strength__score_387_);
return v_res_391_;
}
}
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_Policy_DemoBank_internal__risk__grade__grade(lean_object* v_financial__strength__score_396_, lean_object* v_external__rating__index_397_, lean_object* v_major__red__flag__count_398_, lean_object* v_default__flag_399_){
_start:
{
lean_object* v_g_400_; lean_object* v___x_401_; uint8_t v___x_402_; 
v_g_400_ = lp_BusyBee_BusyBee_Policy_DemoBank_internal__risk__grade(v_financial__strength__score_396_, v_external__rating__index_397_, v_major__red__flag__count_398_, v_default__flag_399_);
v___x_401_ = lean_obj_once(&lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__2, &lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__2_once, _init_lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__2);
v___x_402_ = lean_int_dec_le(v_g_400_, v___x_401_);
if (v___x_402_ == 0)
{
lean_object* v___x_403_; uint8_t v___x_404_; 
v___x_403_ = lean_obj_once(&lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__3, &lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__3_once, _init_lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__3);
v___x_404_ = lean_int_dec_le(v_g_400_, v___x_403_);
if (v___x_404_ == 0)
{
lean_object* v___x_405_; uint8_t v___x_406_; 
v___x_405_ = lean_obj_once(&lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__4, &lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__4_once, _init_lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__4);
v___x_406_ = lean_int_dec_le(v_g_400_, v___x_405_);
lean_dec(v_g_400_);
if (v___x_406_ == 0)
{
lean_object* v___x_407_; 
v___x_407_ = ((lean_object*)(lp_BusyBee_BusyBee_Policy_DemoBank_internal__risk__grade__grade___closed__0));
return v___x_407_;
}
else
{
lean_object* v___x_408_; 
v___x_408_ = ((lean_object*)(lp_BusyBee_BusyBee_Policy_DemoBank_internal__risk__grade__grade___closed__1));
return v___x_408_;
}
}
else
{
lean_object* v___x_409_; 
lean_dec(v_g_400_);
v___x_409_ = ((lean_object*)(lp_BusyBee_BusyBee_Policy_DemoBank_internal__risk__grade__grade___closed__2));
return v___x_409_;
}
}
else
{
lean_object* v___x_410_; 
lean_dec(v_g_400_);
v___x_410_ = ((lean_object*)(lp_BusyBee_BusyBee_Policy_DemoBank_internal__risk__grade__grade___closed__3));
return v___x_410_;
}
}
}
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_Policy_DemoBank_internal__risk__grade__grade___boxed(lean_object* v_financial__strength__score_411_, lean_object* v_external__rating__index_412_, lean_object* v_major__red__flag__count_413_, lean_object* v_default__flag_414_){
_start:
{
lean_object* v_res_415_; 
v_res_415_ = lp_BusyBee_BusyBee_Policy_DemoBank_internal__risk__grade__grade(v_financial__strength__score_411_, v_external__rating__index_412_, v_major__red__flag__count_413_, v_default__flag_414_);
lean_dec(v_default__flag_414_);
lean_dec(v_major__red__flag__count_413_);
lean_dec(v_external__rating__index_412_);
lean_dec(v_financial__strength__score_411_);
return v_res_415_;
}
}
static lean_object* _init_lp_BusyBee_BusyBee_Policy_DemoBank_exposure__percentage___closed__0(void){
_start:
{
lean_object* v___x_416_; lean_object* v___x_417_; 
v___x_416_ = lean_unsigned_to_nat(50u);
v___x_417_ = lean_nat_to_int(v___x_416_);
return v___x_417_;
}
}
static lean_object* _init_lp_BusyBee_BusyBee_Policy_DemoBank_exposure__percentage___closed__1(void){
_start:
{
lean_object* v___x_418_; lean_object* v___x_419_; 
v___x_418_ = lean_unsigned_to_nat(100u);
v___x_419_ = lean_nat_to_int(v___x_418_);
return v___x_419_;
}
}
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_Policy_DemoBank_exposure__percentage(lean_object* v_internal__risk__grade_420_){
_start:
{
lean_object* v___x_421_; uint8_t v___x_422_; 
v___x_421_ = lean_obj_once(&lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__1, &lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__1_once, _init_lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__1);
v___x_422_ = lean_int_dec_le(v_internal__risk__grade_420_, v___x_421_);
if (v___x_422_ == 0)
{
lean_object* v___x_423_; uint8_t v___x_424_; 
v___x_423_ = lean_obj_once(&lp_BusyBee_BusyBee_Policy_DemoBank_interest__cover__points___closed__1, &lp_BusyBee_BusyBee_Policy_DemoBank_interest__cover__points___closed__1_once, _init_lp_BusyBee_BusyBee_Policy_DemoBank_interest__cover__points___closed__1);
v___x_424_ = lean_int_dec_le(v_internal__risk__grade_420_, v___x_423_);
if (v___x_424_ == 0)
{
lean_object* v___x_425_; uint8_t v___x_426_; 
v___x_425_ = lean_obj_once(&lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__3, &lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__3_once, _init_lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__3);
v___x_426_ = lean_int_dec_eq(v_internal__risk__grade_420_, v___x_425_);
if (v___x_426_ == 0)
{
lean_object* v___x_427_; uint8_t v___x_428_; 
v___x_427_ = lean_obj_once(&lp_BusyBee_BusyBee_Policy_DemoBank_interest__cover__points___closed__0, &lp_BusyBee_BusyBee_Policy_DemoBank_interest__cover__points___closed__0_once, _init_lp_BusyBee_BusyBee_Policy_DemoBank_interest__cover__points___closed__0);
v___x_428_ = lean_int_dec_eq(v_internal__risk__grade_420_, v___x_427_);
if (v___x_428_ == 0)
{
lean_object* v___x_429_; 
v___x_429_ = lean_obj_once(&lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__0, &lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__0_once, _init_lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__0);
return v___x_429_;
}
else
{
lean_object* v___x_430_; 
v___x_430_ = lean_obj_once(&lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__8, &lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__8_once, _init_lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__8);
return v___x_430_;
}
}
else
{
lean_object* v___x_431_; 
v___x_431_ = lean_obj_once(&lp_BusyBee_BusyBee_Policy_DemoBank_exposure__percentage___closed__0, &lp_BusyBee_BusyBee_Policy_DemoBank_exposure__percentage___closed__0_once, _init_lp_BusyBee_BusyBee_Policy_DemoBank_exposure__percentage___closed__0);
return v___x_431_;
}
}
else
{
lean_object* v___x_432_; 
v___x_432_ = lean_obj_once(&lp_BusyBee_BusyBee_Policy_DemoBank_base__grade___closed__1, &lp_BusyBee_BusyBee_Policy_DemoBank_base__grade___closed__1_once, _init_lp_BusyBee_BusyBee_Policy_DemoBank_base__grade___closed__1);
return v___x_432_;
}
}
else
{
lean_object* v___x_433_; 
v___x_433_ = lean_obj_once(&lp_BusyBee_BusyBee_Policy_DemoBank_exposure__percentage___closed__1, &lp_BusyBee_BusyBee_Policy_DemoBank_exposure__percentage___closed__1_once, _init_lp_BusyBee_BusyBee_Policy_DemoBank_exposure__percentage___closed__1);
return v___x_433_;
}
}
}
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_Policy_DemoBank_exposure__percentage___boxed(lean_object* v_internal__risk__grade_434_){
_start:
{
lean_object* v_res_435_; 
v_res_435_ = lp_BusyBee_BusyBee_Policy_DemoBank_exposure__percentage(v_internal__risk__grade_434_);
lean_dec(v_internal__risk__grade_434_);
return v_res_435_;
}
}
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_Policy_DemoBank_capped__turnover__x4(lean_object* v_projected__turnover_436_, lean_object* v_audited__turnover_437_){
_start:
{
lean_object* v___x_438_; lean_object* v___x_439_; lean_object* v___x_440_; lean_object* v___x_441_; uint8_t v___x_442_; 
v___x_438_ = lean_obj_once(&lp_BusyBee_BusyBee_Policy_DemoBank_interest__cover__points___closed__1, &lp_BusyBee_BusyBee_Policy_DemoBank_interest__cover__points___closed__1_once, _init_lp_BusyBee_BusyBee_Policy_DemoBank_interest__cover__points___closed__1);
v___x_439_ = lean_int_mul(v___x_438_, v_projected__turnover_436_);
v___x_440_ = lean_obj_once(&lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__3, &lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__3_once, _init_lp_BusyBee_BusyBee_Policy_DemoBank_leverage__points___closed__3);
v___x_441_ = lean_int_mul(v___x_440_, v_audited__turnover_437_);
v___x_442_ = lean_int_dec_le(v___x_439_, v___x_441_);
if (v___x_442_ == 0)
{
lean_dec(v___x_439_);
return v___x_441_;
}
else
{
lean_dec(v___x_441_);
return v___x_439_;
}
}
}
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_Policy_DemoBank_capped__turnover__x4___boxed(lean_object* v_projected__turnover_443_, lean_object* v_audited__turnover_444_){
_start:
{
lean_object* v_res_445_; 
v_res_445_ = lp_BusyBee_BusyBee_Policy_DemoBank_capped__turnover__x4(v_projected__turnover_443_, v_audited__turnover_444_);
lean_dec(v_audited__turnover_444_);
lean_dec(v_projected__turnover_443_);
return v_res_445_;
}
}
static lean_object* _init_lp_BusyBee_BusyBee_Policy_DemoBank_within__exposure__limit___closed__0(void){
_start:
{
lean_object* v___x_446_; lean_object* v___x_447_; 
v___x_446_ = lean_unsigned_to_nat(2000u);
v___x_447_ = lean_nat_to_int(v___x_446_);
return v___x_447_;
}
}
LEAN_EXPORT uint8_t lp_BusyBee_BusyBee_Policy_DemoBank_within__exposure__limit(lean_object* v_proposed__exposure_448_, lean_object* v_projected__turnover_449_, lean_object* v_audited__turnover_450_, lean_object* v_tangible__net__worth_451_, lean_object* v_internal__risk__grade_452_){
_start:
{
lean_object* v_p_453_; lean_object* v___x_454_; lean_object* v___x_455_; lean_object* v___x_456_; lean_object* v___x_457_; uint8_t v___x_458_; 
v_p_453_ = lp_BusyBee_BusyBee_Policy_DemoBank_exposure__percentage(v_internal__risk__grade_452_);
v___x_454_ = lean_obj_once(&lp_BusyBee_BusyBee_Policy_DemoBank_within__exposure__limit___closed__0, &lp_BusyBee_BusyBee_Policy_DemoBank_within__exposure__limit___closed__0_once, _init_lp_BusyBee_BusyBee_Policy_DemoBank_within__exposure__limit___closed__0);
v___x_455_ = lean_int_mul(v___x_454_, v_proposed__exposure_448_);
v___x_456_ = lp_BusyBee_BusyBee_Policy_DemoBank_capped__turnover__x4(v_projected__turnover_449_, v_audited__turnover_450_);
v___x_457_ = lean_int_mul(v_p_453_, v___x_456_);
lean_dec(v___x_456_);
v___x_458_ = lean_int_dec_le(v___x_455_, v___x_457_);
lean_dec(v___x_457_);
lean_dec(v___x_455_);
if (v___x_458_ == 0)
{
lean_dec(v_p_453_);
return v___x_458_;
}
else
{
lean_object* v___x_459_; lean_object* v___x_460_; lean_object* v___x_461_; uint8_t v___x_462_; 
v___x_459_ = lean_obj_once(&lp_BusyBee_BusyBee_Policy_DemoBank_exposure__percentage___closed__1, &lp_BusyBee_BusyBee_Policy_DemoBank_exposure__percentage___closed__1_once, _init_lp_BusyBee_BusyBee_Policy_DemoBank_exposure__percentage___closed__1);
v___x_460_ = lean_int_mul(v___x_459_, v_proposed__exposure_448_);
v___x_461_ = lean_int_mul(v_p_453_, v_tangible__net__worth_451_);
lean_dec(v_p_453_);
v___x_462_ = lean_int_dec_le(v___x_460_, v___x_461_);
lean_dec(v___x_461_);
lean_dec(v___x_460_);
return v___x_462_;
}
}
}
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_Policy_DemoBank_within__exposure__limit___boxed(lean_object* v_proposed__exposure_463_, lean_object* v_projected__turnover_464_, lean_object* v_audited__turnover_465_, lean_object* v_tangible__net__worth_466_, lean_object* v_internal__risk__grade_467_){
_start:
{
uint8_t v_res_468_; lean_object* v_r_469_; 
v_res_468_ = lp_BusyBee_BusyBee_Policy_DemoBank_within__exposure__limit(v_proposed__exposure_463_, v_projected__turnover_464_, v_audited__turnover_465_, v_tangible__net__worth_466_, v_internal__risk__grade_467_);
lean_dec(v_internal__risk__grade_467_);
lean_dec(v_tangible__net__worth_466_);
lean_dec(v_audited__turnover_465_);
lean_dec(v_projected__turnover_464_);
lean_dec(v_proposed__exposure_463_);
v_r_469_ = lean_box(v_res_468_);
return v_r_469_;
}
}
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_Policy_DemoBank_maximum__exposure__test___redArg(lean_object* v_projected__turnover_470_, lean_object* v_audited__turnover_471_, lean_object* v_tangible__net__worth_472_, lean_object* v_internal__risk__grade_473_){
_start:
{
lean_object* v_p_474_; lean_object* v___x_475_; lean_object* v___x_476_; lean_object* v___x_477_; lean_object* v___x_478_; lean_object* v___x_479_; lean_object* v___x_480_; lean_object* v___x_481_; uint8_t v___x_482_; 
v_p_474_ = lp_BusyBee_BusyBee_Policy_DemoBank_exposure__percentage(v_internal__risk__grade_473_);
v___x_475_ = lp_BusyBee_BusyBee_Policy_DemoBank_capped__turnover__x4(v_projected__turnover_470_, v_audited__turnover_471_);
v___x_476_ = lean_int_mul(v_p_474_, v___x_475_);
lean_dec(v___x_475_);
v___x_477_ = lean_obj_once(&lp_BusyBee_BusyBee_Policy_DemoBank_within__exposure__limit___closed__0, &lp_BusyBee_BusyBee_Policy_DemoBank_within__exposure__limit___closed__0_once, _init_lp_BusyBee_BusyBee_Policy_DemoBank_within__exposure__limit___closed__0);
v___x_478_ = lean_int_ediv(v___x_476_, v___x_477_);
lean_dec(v___x_476_);
v___x_479_ = lean_int_mul(v_p_474_, v_tangible__net__worth_472_);
lean_dec(v_p_474_);
v___x_480_ = lean_obj_once(&lp_BusyBee_BusyBee_Policy_DemoBank_exposure__percentage___closed__1, &lp_BusyBee_BusyBee_Policy_DemoBank_exposure__percentage___closed__1_once, _init_lp_BusyBee_BusyBee_Policy_DemoBank_exposure__percentage___closed__1);
v___x_481_ = lean_int_ediv(v___x_479_, v___x_480_);
lean_dec(v___x_479_);
v___x_482_ = lean_int_dec_le(v___x_478_, v___x_481_);
if (v___x_482_ == 0)
{
lean_dec(v___x_478_);
return v___x_481_;
}
else
{
lean_dec(v___x_481_);
return v___x_478_;
}
}
}
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_Policy_DemoBank_maximum__exposure__test___redArg___boxed(lean_object* v_projected__turnover_483_, lean_object* v_audited__turnover_484_, lean_object* v_tangible__net__worth_485_, lean_object* v_internal__risk__grade_486_){
_start:
{
lean_object* v_res_487_; 
v_res_487_ = lp_BusyBee_BusyBee_Policy_DemoBank_maximum__exposure__test___redArg(v_projected__turnover_483_, v_audited__turnover_484_, v_tangible__net__worth_485_, v_internal__risk__grade_486_);
lean_dec(v_internal__risk__grade_486_);
lean_dec(v_tangible__net__worth_485_);
lean_dec(v_audited__turnover_484_);
lean_dec(v_projected__turnover_483_);
return v_res_487_;
}
}
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_Policy_DemoBank_maximum__exposure__test(lean_object* v___proposed__exposure_488_, lean_object* v_projected__turnover_489_, lean_object* v_audited__turnover_490_, lean_object* v_tangible__net__worth_491_, lean_object* v_internal__risk__grade_492_){
_start:
{
lean_object* v___x_493_; 
v___x_493_ = lp_BusyBee_BusyBee_Policy_DemoBank_maximum__exposure__test___redArg(v_projected__turnover_489_, v_audited__turnover_490_, v_tangible__net__worth_491_, v_internal__risk__grade_492_);
return v___x_493_;
}
}
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_Policy_DemoBank_maximum__exposure__test___boxed(lean_object* v___proposed__exposure_494_, lean_object* v_projected__turnover_495_, lean_object* v_audited__turnover_496_, lean_object* v_tangible__net__worth_497_, lean_object* v_internal__risk__grade_498_){
_start:
{
lean_object* v_res_499_; 
v_res_499_ = lp_BusyBee_BusyBee_Policy_DemoBank_maximum__exposure__test(v___proposed__exposure_494_, v_projected__turnover_495_, v_audited__turnover_496_, v_tangible__net__worth_497_, v_internal__risk__grade_498_);
lean_dec(v_internal__risk__grade_498_);
lean_dec(v_tangible__net__worth_497_);
lean_dec(v_audited__turnover_496_);
lean_dec(v_projected__turnover_495_);
lean_dec(v___proposed__exposure_494_);
return v_res_499_;
}
}
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_Policy_DemoBank_maximum__exposure__test__grade(lean_object* v_proposed__exposure_502_, lean_object* v_projected__turnover_503_, lean_object* v_audited__turnover_504_, lean_object* v_tangible__net__worth_505_, lean_object* v_internal__risk__grade_506_){
_start:
{
uint8_t v___x_507_; 
v___x_507_ = lp_BusyBee_BusyBee_Policy_DemoBank_within__exposure__limit(v_proposed__exposure_502_, v_projected__turnover_503_, v_audited__turnover_504_, v_tangible__net__worth_505_, v_internal__risk__grade_506_);
if (v___x_507_ == 0)
{
lean_object* v___x_508_; 
v___x_508_ = ((lean_object*)(lp_BusyBee_BusyBee_Policy_DemoBank_maximum__exposure__test__grade___closed__0));
return v___x_508_;
}
else
{
lean_object* v___x_509_; 
v___x_509_ = ((lean_object*)(lp_BusyBee_BusyBee_Policy_DemoBank_maximum__exposure__test__grade___closed__1));
return v___x_509_;
}
}
}
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_Policy_DemoBank_maximum__exposure__test__grade___boxed(lean_object* v_proposed__exposure_510_, lean_object* v_projected__turnover_511_, lean_object* v_audited__turnover_512_, lean_object* v_tangible__net__worth_513_, lean_object* v_internal__risk__grade_514_){
_start:
{
lean_object* v_res_515_; 
v_res_515_ = lp_BusyBee_BusyBee_Policy_DemoBank_maximum__exposure__test__grade(v_proposed__exposure_510_, v_projected__turnover_511_, v_audited__turnover_512_, v_tangible__net__worth_513_, v_internal__risk__grade_514_);
lean_dec(v_internal__risk__grade_514_);
lean_dec(v_tangible__net__worth_513_);
lean_dec(v_audited__turnover_512_);
lean_dec(v_projected__turnover_511_);
lean_dec(v_proposed__exposure_510_);
return v_res_515_;
}
}
lean_object* initialize_Init(uint8_t builtin);
lean_object* initialize_Init(uint8_t builtin);
lean_object* initialize_BusyBee_BusyBee_Common(uint8_t builtin);
void lean_initialize_runtime_module();
static bool _G_initialized = false;
LEAN_EXPORT lean_object* initialize_BusyBee_BusyBee_Policy_DemoBank(uint8_t builtin) {
lean_object * res;
if (_G_initialized) return lean_io_result_mk_ok(lean_box(0));
_G_initialized = true;
lean_initialize_runtime_module();
res = initialize_Init(builtin);
if (lean_io_result_is_error(res)) return res;
lean_dec_ref(res);
res = initialize_Init(builtin);
if (lean_io_result_is_error(res)) return res;
lean_dec_ref(res);
res = initialize_BusyBee_BusyBee_Common(builtin);
if (lean_io_result_is_error(res)) return res;
lean_dec_ref(res);
return lean_io_result_mk_ok(lean_box(0));
}
#ifdef __cplusplus
}
#endif
