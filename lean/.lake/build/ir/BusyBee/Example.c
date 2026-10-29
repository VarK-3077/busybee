// Lean compiler output
// Module: BusyBee.Example
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
lean_object* lean_int_mul(lean_object*, lean_object*);
uint8_t lp_BusyBee_BusyBee_gradeAtMost(lean_object*, lean_object*);
static lean_once_cell_t lp_BusyBee_BusyBee_Example_netDebt___closed__0_once = LEAN_ONCE_CELL_INITIALIZER;
static lean_object* lp_BusyBee_BusyBee_Example_netDebt___closed__0;
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_Example_netDebt;
static lean_once_cell_t lp_BusyBee_BusyBee_Example_ebitda___closed__0_once = LEAN_ONCE_CELL_INITIALIZER;
static lean_object* lp_BusyBee_BusyBee_Example_ebitda___closed__0;
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_Example_ebitda;
static lean_once_cell_t lp_BusyBee_BusyBee_Example_interest___closed__0_once = LEAN_ONCE_CELL_INITIALIZER;
static lean_object* lp_BusyBee_BusyBee_Example_interest___closed__0;
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_Example_interest;
static lean_once_cell_t lp_BusyBee_BusyBee_Example_leverageGrade___closed__0_once = LEAN_ONCE_CELL_INITIALIZER;
static lean_object* lp_BusyBee_BusyBee_Example_leverageGrade___closed__0;
static lean_once_cell_t lp_BusyBee_BusyBee_Example_leverageGrade___closed__1_once = LEAN_ONCE_CELL_INITIALIZER;
static lean_object* lp_BusyBee_BusyBee_Example_leverageGrade___closed__1;
static lean_once_cell_t lp_BusyBee_BusyBee_Example_leverageGrade___closed__2_once = LEAN_ONCE_CELL_INITIALIZER;
static lean_object* lp_BusyBee_BusyBee_Example_leverageGrade___closed__2;
static lean_once_cell_t lp_BusyBee_BusyBee_Example_leverageGrade___closed__3_once = LEAN_ONCE_CELL_INITIALIZER;
static lean_object* lp_BusyBee_BusyBee_Example_leverageGrade___closed__3;
static lean_once_cell_t lp_BusyBee_BusyBee_Example_leverageGrade___closed__4_once = LEAN_ONCE_CELL_INITIALIZER;
static uint8_t lp_BusyBee_BusyBee_Example_leverageGrade___closed__4;
LEAN_EXPORT uint8_t lp_BusyBee_BusyBee_Example_leverageGrade;
static lean_object* _init_lp_BusyBee_BusyBee_Example_netDebt___closed__0(void){
_start:
{
lean_object* v___x_1_; lean_object* v___x_2_; 
v___x_1_ = lean_unsigned_to_nat(125000u);
v___x_2_ = lean_nat_to_int(v___x_1_);
return v___x_2_;
}
}
static lean_object* _init_lp_BusyBee_BusyBee_Example_netDebt(void){
_start:
{
lean_object* v___x_3_; 
v___x_3_ = lean_obj_once(&lp_BusyBee_BusyBee_Example_netDebt___closed__0, &lp_BusyBee_BusyBee_Example_netDebt___closed__0_once, _init_lp_BusyBee_BusyBee_Example_netDebt___closed__0);
return v___x_3_;
}
}
static lean_object* _init_lp_BusyBee_BusyBee_Example_ebitda___closed__0(void){
_start:
{
lean_object* v___x_4_; lean_object* v___x_5_; 
v___x_4_ = lean_unsigned_to_nat(42000u);
v___x_5_ = lean_nat_to_int(v___x_4_);
return v___x_5_;
}
}
static lean_object* _init_lp_BusyBee_BusyBee_Example_ebitda(void){
_start:
{
lean_object* v___x_6_; 
v___x_6_ = lean_obj_once(&lp_BusyBee_BusyBee_Example_ebitda___closed__0, &lp_BusyBee_BusyBee_Example_ebitda___closed__0_once, _init_lp_BusyBee_BusyBee_Example_ebitda___closed__0);
return v___x_6_;
}
}
static lean_object* _init_lp_BusyBee_BusyBee_Example_interest___closed__0(void){
_start:
{
lean_object* v___x_7_; lean_object* v___x_8_; 
v___x_7_ = lean_unsigned_to_nat(15000u);
v___x_8_ = lean_nat_to_int(v___x_7_);
return v___x_8_;
}
}
static lean_object* _init_lp_BusyBee_BusyBee_Example_interest(void){
_start:
{
lean_object* v___x_9_; 
v___x_9_ = lean_obj_once(&lp_BusyBee_BusyBee_Example_interest___closed__0, &lp_BusyBee_BusyBee_Example_interest___closed__0_once, _init_lp_BusyBee_BusyBee_Example_interest___closed__0);
return v___x_9_;
}
}
static lean_object* _init_lp_BusyBee_BusyBee_Example_leverageGrade___closed__0(void){
_start:
{
lean_object* v___x_10_; lean_object* v___x_11_; 
v___x_10_ = lean_unsigned_to_nat(2u);
v___x_11_ = lean_nat_to_int(v___x_10_);
return v___x_11_;
}
}
static lean_object* _init_lp_BusyBee_BusyBee_Example_leverageGrade___closed__1(void){
_start:
{
lean_object* v___x_12_; lean_object* v___x_13_; lean_object* v___x_14_; 
v___x_12_ = lp_BusyBee_BusyBee_Example_netDebt;
v___x_13_ = lean_obj_once(&lp_BusyBee_BusyBee_Example_leverageGrade___closed__0, &lp_BusyBee_BusyBee_Example_leverageGrade___closed__0_once, _init_lp_BusyBee_BusyBee_Example_leverageGrade___closed__0);
v___x_14_ = lean_int_mul(v___x_13_, v___x_12_);
return v___x_14_;
}
}
static lean_object* _init_lp_BusyBee_BusyBee_Example_leverageGrade___closed__2(void){
_start:
{
lean_object* v___x_15_; lean_object* v___x_16_; 
v___x_15_ = lean_unsigned_to_nat(7u);
v___x_16_ = lean_nat_to_int(v___x_15_);
return v___x_16_;
}
}
static lean_object* _init_lp_BusyBee_BusyBee_Example_leverageGrade___closed__3(void){
_start:
{
lean_object* v___x_17_; lean_object* v___x_18_; lean_object* v___x_19_; 
v___x_17_ = lp_BusyBee_BusyBee_Example_ebitda;
v___x_18_ = lean_obj_once(&lp_BusyBee_BusyBee_Example_leverageGrade___closed__2, &lp_BusyBee_BusyBee_Example_leverageGrade___closed__2_once, _init_lp_BusyBee_BusyBee_Example_leverageGrade___closed__2);
v___x_19_ = lean_int_mul(v___x_18_, v___x_17_);
return v___x_19_;
}
}
static uint8_t _init_lp_BusyBee_BusyBee_Example_leverageGrade___closed__4(void){
_start:
{
lean_object* v___x_20_; lean_object* v___x_21_; uint8_t v___x_22_; 
v___x_20_ = lean_obj_once(&lp_BusyBee_BusyBee_Example_leverageGrade___closed__3, &lp_BusyBee_BusyBee_Example_leverageGrade___closed__3_once, _init_lp_BusyBee_BusyBee_Example_leverageGrade___closed__3);
v___x_21_ = lean_obj_once(&lp_BusyBee_BusyBee_Example_leverageGrade___closed__1, &lp_BusyBee_BusyBee_Example_leverageGrade___closed__1_once, _init_lp_BusyBee_BusyBee_Example_leverageGrade___closed__1);
v___x_22_ = lp_BusyBee_BusyBee_gradeAtMost(v___x_21_, v___x_20_);
return v___x_22_;
}
}
static uint8_t _init_lp_BusyBee_BusyBee_Example_leverageGrade(void){
_start:
{
uint8_t v___x_23_; 
v___x_23_ = lean_uint8_once(&lp_BusyBee_BusyBee_Example_leverageGrade___closed__4, &lp_BusyBee_BusyBee_Example_leverageGrade___closed__4_once, _init_lp_BusyBee_BusyBee_Example_leverageGrade___closed__4);
return v___x_23_;
}
}
lean_object* initialize_Init(uint8_t builtin);
lean_object* initialize_Init(uint8_t builtin);
lean_object* initialize_BusyBee_BusyBee_Common(uint8_t builtin);
void lean_initialize_runtime_module();
static bool _G_initialized = false;
LEAN_EXPORT lean_object* initialize_BusyBee_BusyBee_Example(uint8_t builtin) {
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
lp_BusyBee_BusyBee_Example_netDebt = _init_lp_BusyBee_BusyBee_Example_netDebt();
lean_mark_persistent(lp_BusyBee_BusyBee_Example_netDebt);
lp_BusyBee_BusyBee_Example_ebitda = _init_lp_BusyBee_BusyBee_Example_ebitda();
lean_mark_persistent(lp_BusyBee_BusyBee_Example_ebitda);
lp_BusyBee_BusyBee_Example_interest = _init_lp_BusyBee_BusyBee_Example_interest();
lean_mark_persistent(lp_BusyBee_BusyBee_Example_interest);
lp_BusyBee_BusyBee_Example_leverageGrade = _init_lp_BusyBee_BusyBee_Example_leverageGrade();
return lean_io_result_mk_ok(lean_box(0));
}
#ifdef __cplusplus
}
#endif
