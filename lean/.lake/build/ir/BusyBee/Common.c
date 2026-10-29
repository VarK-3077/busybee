// Lean compiler output
// Module: BusyBee.Common
// Imports: public import Init public meta import Init
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
uint8_t lean_nat_dec_eq(lean_object*, lean_object*);
uint8_t lean_int_dec_le(lean_object*, lean_object*);
lean_object* lean_nat_to_int(lean_object*);
lean_object* lean_int_mul(lean_object*, lean_object*);
uint8_t lean_nat_dec_le(lean_object*, lean_object*);
lean_object* l_Repr_addAppParen(lean_object*, lean_object*);
uint8_t lean_nat_dec_le(lean_object*, lean_object*);
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_Grade_ctorIdx(uint8_t);
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_Grade_ctorIdx___boxed(lean_object*);
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_Grade_ctorElim___redArg(lean_object*);
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_Grade_ctorElim___redArg___boxed(lean_object*);
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_Grade_ctorElim(lean_object*, lean_object*, uint8_t, lean_object*, lean_object*);
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_Grade_ctorElim___boxed(lean_object*, lean_object*, lean_object*, lean_object*, lean_object*);
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_Grade_pass_elim___redArg(lean_object*);
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_Grade_pass_elim___redArg___boxed(lean_object*);
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_Grade_pass_elim(lean_object*, uint8_t, lean_object*, lean_object*);
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_Grade_pass_elim___boxed(lean_object*, lean_object*, lean_object*, lean_object*);
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_Grade_watch_elim___redArg(lean_object*);
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_Grade_watch_elim___redArg___boxed(lean_object*);
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_Grade_watch_elim(lean_object*, uint8_t, lean_object*, lean_object*);
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_Grade_watch_elim___boxed(lean_object*, lean_object*, lean_object*, lean_object*);
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_Grade_fail_elim___redArg(lean_object*);
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_Grade_fail_elim___redArg___boxed(lean_object*);
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_Grade_fail_elim(lean_object*, uint8_t, lean_object*, lean_object*);
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_Grade_fail_elim___boxed(lean_object*, lean_object*, lean_object*, lean_object*);
LEAN_EXPORT uint8_t lp_BusyBee_BusyBee_Grade_ofNat(lean_object*);
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_Grade_ofNat___boxed(lean_object*);
LEAN_EXPORT uint8_t lp_BusyBee_BusyBee_instDecidableEqGrade(uint8_t, uint8_t);
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_instDecidableEqGrade___boxed(lean_object*, lean_object*);
static const lean_string_object lp_BusyBee_BusyBee_instReprGrade_repr___closed__0_value = {.m_header = {.m_rc = 0, .m_cs_sz = 0, .m_other = 0, .m_tag = 249}, .m_size = 19, .m_capacity = 19, .m_length = 18, .m_data = "BusyBee.Grade.pass"};
static const lean_object* lp_BusyBee_BusyBee_instReprGrade_repr___closed__0 = (const lean_object*)&lp_BusyBee_BusyBee_instReprGrade_repr___closed__0_value;
static const lean_ctor_object lp_BusyBee_BusyBee_instReprGrade_repr___closed__1_value = {.m_header = {.m_rc = 0, .m_cs_sz = sizeof(lean_ctor_object) + sizeof(void*)*1 + 0, .m_other = 1, .m_tag = 3}, .m_objs = {((lean_object*)&lp_BusyBee_BusyBee_instReprGrade_repr___closed__0_value)}};
static const lean_object* lp_BusyBee_BusyBee_instReprGrade_repr___closed__1 = (const lean_object*)&lp_BusyBee_BusyBee_instReprGrade_repr___closed__1_value;
static const lean_string_object lp_BusyBee_BusyBee_instReprGrade_repr___closed__2_value = {.m_header = {.m_rc = 0, .m_cs_sz = 0, .m_other = 0, .m_tag = 249}, .m_size = 20, .m_capacity = 20, .m_length = 19, .m_data = "BusyBee.Grade.watch"};
static const lean_object* lp_BusyBee_BusyBee_instReprGrade_repr___closed__2 = (const lean_object*)&lp_BusyBee_BusyBee_instReprGrade_repr___closed__2_value;
static const lean_ctor_object lp_BusyBee_BusyBee_instReprGrade_repr___closed__3_value = {.m_header = {.m_rc = 0, .m_cs_sz = sizeof(lean_ctor_object) + sizeof(void*)*1 + 0, .m_other = 1, .m_tag = 3}, .m_objs = {((lean_object*)&lp_BusyBee_BusyBee_instReprGrade_repr___closed__2_value)}};
static const lean_object* lp_BusyBee_BusyBee_instReprGrade_repr___closed__3 = (const lean_object*)&lp_BusyBee_BusyBee_instReprGrade_repr___closed__3_value;
static const lean_string_object lp_BusyBee_BusyBee_instReprGrade_repr___closed__4_value = {.m_header = {.m_rc = 0, .m_cs_sz = 0, .m_other = 0, .m_tag = 249}, .m_size = 19, .m_capacity = 19, .m_length = 18, .m_data = "BusyBee.Grade.fail"};
static const lean_object* lp_BusyBee_BusyBee_instReprGrade_repr___closed__4 = (const lean_object*)&lp_BusyBee_BusyBee_instReprGrade_repr___closed__4_value;
static const lean_ctor_object lp_BusyBee_BusyBee_instReprGrade_repr___closed__5_value = {.m_header = {.m_rc = 0, .m_cs_sz = sizeof(lean_ctor_object) + sizeof(void*)*1 + 0, .m_other = 1, .m_tag = 3}, .m_objs = {((lean_object*)&lp_BusyBee_BusyBee_instReprGrade_repr___closed__4_value)}};
static const lean_object* lp_BusyBee_BusyBee_instReprGrade_repr___closed__5 = (const lean_object*)&lp_BusyBee_BusyBee_instReprGrade_repr___closed__5_value;
static lean_once_cell_t lp_BusyBee_BusyBee_instReprGrade_repr___closed__6_once = LEAN_ONCE_CELL_INITIALIZER;
static lean_object* lp_BusyBee_BusyBee_instReprGrade_repr___closed__6;
static lean_once_cell_t lp_BusyBee_BusyBee_instReprGrade_repr___closed__7_once = LEAN_ONCE_CELL_INITIALIZER;
static lean_object* lp_BusyBee_BusyBee_instReprGrade_repr___closed__7;
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_instReprGrade_repr(uint8_t, lean_object*);
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_instReprGrade_repr___boxed(lean_object*, lean_object*);
static const lean_closure_object lp_BusyBee_BusyBee_instReprGrade___closed__0_value = {.m_header = {.m_rc = 0, .m_cs_sz = sizeof(lean_closure_object) + sizeof(void*)*0, .m_other = 0, .m_tag = 245}, .m_fun = (void*)lp_BusyBee_BusyBee_instReprGrade_repr___boxed, .m_arity = 2, .m_num_fixed = 0, .m_objs = {} };
static const lean_object* lp_BusyBee_BusyBee_instReprGrade___closed__0 = (const lean_object*)&lp_BusyBee_BusyBee_instReprGrade___closed__0_value;
LEAN_EXPORT const lean_object* lp_BusyBee_BusyBee_instReprGrade = (const lean_object*)&lp_BusyBee_BusyBee_instReprGrade___closed__0_value;
LEAN_EXPORT uint8_t lp_BusyBee_BusyBee_instInhabitedGrade_default;
LEAN_EXPORT uint8_t lp_BusyBee_BusyBee_instInhabitedGrade;
LEAN_EXPORT uint8_t lp_BusyBee_BusyBee_gradeAtMost(lean_object*, lean_object*);
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_gradeAtMost___boxed(lean_object*, lean_object*);
LEAN_EXPORT uint8_t lp_BusyBee_BusyBee_gradeBps(lean_object*, lean_object*);
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_gradeBps___boxed(lean_object*, lean_object*);
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_Grade_ctorIdx(uint8_t v_x_1_){
_start:
{
switch(v_x_1_)
{
case 0:
{
lean_object* v___x_2_; 
v___x_2_ = lean_unsigned_to_nat(0u);
return v___x_2_;
}
case 1:
{
lean_object* v___x_3_; 
v___x_3_ = lean_unsigned_to_nat(1u);
return v___x_3_;
}
default: 
{
lean_object* v___x_4_; 
v___x_4_ = lean_unsigned_to_nat(2u);
return v___x_4_;
}
}
}
}
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_Grade_ctorIdx___boxed(lean_object* v_x_5_){
_start:
{
uint8_t v_x_boxed_6_; lean_object* v_res_7_; 
v_x_boxed_6_ = lean_unbox(v_x_5_);
v_res_7_ = lp_BusyBee_BusyBee_Grade_ctorIdx(v_x_boxed_6_);
return v_res_7_;
}
}
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_Grade_ctorElim___redArg(lean_object* v_k_8_){
_start:
{
lean_inc(v_k_8_);
return v_k_8_;
}
}
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_Grade_ctorElim___redArg___boxed(lean_object* v_k_9_){
_start:
{
lean_object* v_res_10_; 
v_res_10_ = lp_BusyBee_BusyBee_Grade_ctorElim___redArg(v_k_9_);
lean_dec(v_k_9_);
return v_res_10_;
}
}
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_Grade_ctorElim(lean_object* v_motive_11_, lean_object* v_ctorIdx_12_, uint8_t v_t_13_, lean_object* v_h_14_, lean_object* v_k_15_){
_start:
{
lean_inc(v_k_15_);
return v_k_15_;
}
}
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_Grade_ctorElim___boxed(lean_object* v_motive_16_, lean_object* v_ctorIdx_17_, lean_object* v_t_18_, lean_object* v_h_19_, lean_object* v_k_20_){
_start:
{
uint8_t v_t_boxed_21_; lean_object* v_res_22_; 
v_t_boxed_21_ = lean_unbox(v_t_18_);
v_res_22_ = lp_BusyBee_BusyBee_Grade_ctorElim(v_motive_16_, v_ctorIdx_17_, v_t_boxed_21_, v_h_19_, v_k_20_);
lean_dec(v_k_20_);
lean_dec(v_ctorIdx_17_);
return v_res_22_;
}
}
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_Grade_pass_elim___redArg(lean_object* v_pass_23_){
_start:
{
lean_inc(v_pass_23_);
return v_pass_23_;
}
}
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_Grade_pass_elim___redArg___boxed(lean_object* v_pass_24_){
_start:
{
lean_object* v_res_25_; 
v_res_25_ = lp_BusyBee_BusyBee_Grade_pass_elim___redArg(v_pass_24_);
lean_dec(v_pass_24_);
return v_res_25_;
}
}
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_Grade_pass_elim(lean_object* v_motive_26_, uint8_t v_t_27_, lean_object* v_h_28_, lean_object* v_pass_29_){
_start:
{
lean_inc(v_pass_29_);
return v_pass_29_;
}
}
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_Grade_pass_elim___boxed(lean_object* v_motive_30_, lean_object* v_t_31_, lean_object* v_h_32_, lean_object* v_pass_33_){
_start:
{
uint8_t v_t_boxed_34_; lean_object* v_res_35_; 
v_t_boxed_34_ = lean_unbox(v_t_31_);
v_res_35_ = lp_BusyBee_BusyBee_Grade_pass_elim(v_motive_30_, v_t_boxed_34_, v_h_32_, v_pass_33_);
lean_dec(v_pass_33_);
return v_res_35_;
}
}
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_Grade_watch_elim___redArg(lean_object* v_watch_36_){
_start:
{
lean_inc(v_watch_36_);
return v_watch_36_;
}
}
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_Grade_watch_elim___redArg___boxed(lean_object* v_watch_37_){
_start:
{
lean_object* v_res_38_; 
v_res_38_ = lp_BusyBee_BusyBee_Grade_watch_elim___redArg(v_watch_37_);
lean_dec(v_watch_37_);
return v_res_38_;
}
}
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_Grade_watch_elim(lean_object* v_motive_39_, uint8_t v_t_40_, lean_object* v_h_41_, lean_object* v_watch_42_){
_start:
{
lean_inc(v_watch_42_);
return v_watch_42_;
}
}
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_Grade_watch_elim___boxed(lean_object* v_motive_43_, lean_object* v_t_44_, lean_object* v_h_45_, lean_object* v_watch_46_){
_start:
{
uint8_t v_t_boxed_47_; lean_object* v_res_48_; 
v_t_boxed_47_ = lean_unbox(v_t_44_);
v_res_48_ = lp_BusyBee_BusyBee_Grade_watch_elim(v_motive_43_, v_t_boxed_47_, v_h_45_, v_watch_46_);
lean_dec(v_watch_46_);
return v_res_48_;
}
}
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_Grade_fail_elim___redArg(lean_object* v_fail_49_){
_start:
{
lean_inc(v_fail_49_);
return v_fail_49_;
}
}
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_Grade_fail_elim___redArg___boxed(lean_object* v_fail_50_){
_start:
{
lean_object* v_res_51_; 
v_res_51_ = lp_BusyBee_BusyBee_Grade_fail_elim___redArg(v_fail_50_);
lean_dec(v_fail_50_);
return v_res_51_;
}
}
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_Grade_fail_elim(lean_object* v_motive_52_, uint8_t v_t_53_, lean_object* v_h_54_, lean_object* v_fail_55_){
_start:
{
lean_inc(v_fail_55_);
return v_fail_55_;
}
}
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_Grade_fail_elim___boxed(lean_object* v_motive_56_, lean_object* v_t_57_, lean_object* v_h_58_, lean_object* v_fail_59_){
_start:
{
uint8_t v_t_boxed_60_; lean_object* v_res_61_; 
v_t_boxed_60_ = lean_unbox(v_t_57_);
v_res_61_ = lp_BusyBee_BusyBee_Grade_fail_elim(v_motive_56_, v_t_boxed_60_, v_h_58_, v_fail_59_);
lean_dec(v_fail_59_);
return v_res_61_;
}
}
LEAN_EXPORT uint8_t lp_BusyBee_BusyBee_Grade_ofNat(lean_object* v_n_62_){
_start:
{
lean_object* v___x_63_; uint8_t v___x_64_; 
v___x_63_ = lean_unsigned_to_nat(0u);
v___x_64_ = lean_nat_dec_le(v_n_62_, v___x_63_);
if (v___x_64_ == 0)
{
lean_object* v___x_65_; uint8_t v___x_66_; 
v___x_65_ = lean_unsigned_to_nat(1u);
v___x_66_ = lean_nat_dec_le(v_n_62_, v___x_65_);
if (v___x_66_ == 0)
{
uint8_t v___x_67_; 
v___x_67_ = 2;
return v___x_67_;
}
else
{
uint8_t v___x_68_; 
v___x_68_ = 1;
return v___x_68_;
}
}
else
{
uint8_t v___x_69_; 
v___x_69_ = 0;
return v___x_69_;
}
}
}
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_Grade_ofNat___boxed(lean_object* v_n_70_){
_start:
{
uint8_t v_res_71_; lean_object* v_r_72_; 
v_res_71_ = lp_BusyBee_BusyBee_Grade_ofNat(v_n_70_);
lean_dec(v_n_70_);
v_r_72_ = lean_box(v_res_71_);
return v_r_72_;
}
}
LEAN_EXPORT uint8_t lp_BusyBee_BusyBee_instDecidableEqGrade(uint8_t v_x_73_, uint8_t v_y_74_){
_start:
{
lean_object* v___x_75_; lean_object* v___x_76_; uint8_t v___x_77_; 
v___x_75_ = lp_BusyBee_BusyBee_Grade_ctorIdx(v_x_73_);
v___x_76_ = lp_BusyBee_BusyBee_Grade_ctorIdx(v_y_74_);
v___x_77_ = lean_nat_dec_eq(v___x_75_, v___x_76_);
lean_dec(v___x_76_);
lean_dec(v___x_75_);
return v___x_77_;
}
}
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_instDecidableEqGrade___boxed(lean_object* v_x_78_, lean_object* v_y_79_){
_start:
{
uint8_t v_x_20__boxed_80_; uint8_t v_y_21__boxed_81_; uint8_t v_res_82_; lean_object* v_r_83_; 
v_x_20__boxed_80_ = lean_unbox(v_x_78_);
v_y_21__boxed_81_ = lean_unbox(v_y_79_);
v_res_82_ = lp_BusyBee_BusyBee_instDecidableEqGrade(v_x_20__boxed_80_, v_y_21__boxed_81_);
v_r_83_ = lean_box(v_res_82_);
return v_r_83_;
}
}
static lean_object* _init_lp_BusyBee_BusyBee_instReprGrade_repr___closed__6(void){
_start:
{
lean_object* v___x_93_; lean_object* v___x_94_; 
v___x_93_ = lean_unsigned_to_nat(2u);
v___x_94_ = lean_nat_to_int(v___x_93_);
return v___x_94_;
}
}
static lean_object* _init_lp_BusyBee_BusyBee_instReprGrade_repr___closed__7(void){
_start:
{
lean_object* v___x_95_; lean_object* v___x_96_; 
v___x_95_ = lean_unsigned_to_nat(1u);
v___x_96_ = lean_nat_to_int(v___x_95_);
return v___x_96_;
}
}
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_instReprGrade_repr(uint8_t v_x_97_, lean_object* v_prec_98_){
_start:
{
lean_object* v___y_100_; lean_object* v___y_107_; lean_object* v___y_114_; 
switch(v_x_97_)
{
case 0:
{
lean_object* v___x_120_; uint8_t v___x_121_; 
v___x_120_ = lean_unsigned_to_nat(1024u);
v___x_121_ = lean_nat_dec_le(v___x_120_, v_prec_98_);
if (v___x_121_ == 0)
{
lean_object* v___x_122_; 
v___x_122_ = lean_obj_once(&lp_BusyBee_BusyBee_instReprGrade_repr___closed__6, &lp_BusyBee_BusyBee_instReprGrade_repr___closed__6_once, _init_lp_BusyBee_BusyBee_instReprGrade_repr___closed__6);
v___y_100_ = v___x_122_;
goto v___jp_99_;
}
else
{
lean_object* v___x_123_; 
v___x_123_ = lean_obj_once(&lp_BusyBee_BusyBee_instReprGrade_repr___closed__7, &lp_BusyBee_BusyBee_instReprGrade_repr___closed__7_once, _init_lp_BusyBee_BusyBee_instReprGrade_repr___closed__7);
v___y_100_ = v___x_123_;
goto v___jp_99_;
}
}
case 1:
{
lean_object* v___x_124_; uint8_t v___x_125_; 
v___x_124_ = lean_unsigned_to_nat(1024u);
v___x_125_ = lean_nat_dec_le(v___x_124_, v_prec_98_);
if (v___x_125_ == 0)
{
lean_object* v___x_126_; 
v___x_126_ = lean_obj_once(&lp_BusyBee_BusyBee_instReprGrade_repr___closed__6, &lp_BusyBee_BusyBee_instReprGrade_repr___closed__6_once, _init_lp_BusyBee_BusyBee_instReprGrade_repr___closed__6);
v___y_107_ = v___x_126_;
goto v___jp_106_;
}
else
{
lean_object* v___x_127_; 
v___x_127_ = lean_obj_once(&lp_BusyBee_BusyBee_instReprGrade_repr___closed__7, &lp_BusyBee_BusyBee_instReprGrade_repr___closed__7_once, _init_lp_BusyBee_BusyBee_instReprGrade_repr___closed__7);
v___y_107_ = v___x_127_;
goto v___jp_106_;
}
}
default: 
{
lean_object* v___x_128_; uint8_t v___x_129_; 
v___x_128_ = lean_unsigned_to_nat(1024u);
v___x_129_ = lean_nat_dec_le(v___x_128_, v_prec_98_);
if (v___x_129_ == 0)
{
lean_object* v___x_130_; 
v___x_130_ = lean_obj_once(&lp_BusyBee_BusyBee_instReprGrade_repr___closed__6, &lp_BusyBee_BusyBee_instReprGrade_repr___closed__6_once, _init_lp_BusyBee_BusyBee_instReprGrade_repr___closed__6);
v___y_114_ = v___x_130_;
goto v___jp_113_;
}
else
{
lean_object* v___x_131_; 
v___x_131_ = lean_obj_once(&lp_BusyBee_BusyBee_instReprGrade_repr___closed__7, &lp_BusyBee_BusyBee_instReprGrade_repr___closed__7_once, _init_lp_BusyBee_BusyBee_instReprGrade_repr___closed__7);
v___y_114_ = v___x_131_;
goto v___jp_113_;
}
}
}
v___jp_99_:
{
lean_object* v___x_101_; lean_object* v___x_102_; uint8_t v___x_103_; lean_object* v___x_104_; lean_object* v___x_105_; 
v___x_101_ = ((lean_object*)(lp_BusyBee_BusyBee_instReprGrade_repr___closed__1));
lean_inc(v___y_100_);
v___x_102_ = lean_alloc_ctor(4, 2, 0);
lean_ctor_set(v___x_102_, 0, v___y_100_);
lean_ctor_set(v___x_102_, 1, v___x_101_);
v___x_103_ = 0;
v___x_104_ = lean_alloc_ctor(6, 1, 1);
lean_ctor_set(v___x_104_, 0, v___x_102_);
lean_ctor_set_uint8(v___x_104_, sizeof(void*)*1, v___x_103_);
v___x_105_ = l_Repr_addAppParen(v___x_104_, v_prec_98_);
return v___x_105_;
}
v___jp_106_:
{
lean_object* v___x_108_; lean_object* v___x_109_; uint8_t v___x_110_; lean_object* v___x_111_; lean_object* v___x_112_; 
v___x_108_ = ((lean_object*)(lp_BusyBee_BusyBee_instReprGrade_repr___closed__3));
lean_inc(v___y_107_);
v___x_109_ = lean_alloc_ctor(4, 2, 0);
lean_ctor_set(v___x_109_, 0, v___y_107_);
lean_ctor_set(v___x_109_, 1, v___x_108_);
v___x_110_ = 0;
v___x_111_ = lean_alloc_ctor(6, 1, 1);
lean_ctor_set(v___x_111_, 0, v___x_109_);
lean_ctor_set_uint8(v___x_111_, sizeof(void*)*1, v___x_110_);
v___x_112_ = l_Repr_addAppParen(v___x_111_, v_prec_98_);
return v___x_112_;
}
v___jp_113_:
{
lean_object* v___x_115_; lean_object* v___x_116_; uint8_t v___x_117_; lean_object* v___x_118_; lean_object* v___x_119_; 
v___x_115_ = ((lean_object*)(lp_BusyBee_BusyBee_instReprGrade_repr___closed__5));
lean_inc(v___y_114_);
v___x_116_ = lean_alloc_ctor(4, 2, 0);
lean_ctor_set(v___x_116_, 0, v___y_114_);
lean_ctor_set(v___x_116_, 1, v___x_115_);
v___x_117_ = 0;
v___x_118_ = lean_alloc_ctor(6, 1, 1);
lean_ctor_set(v___x_118_, 0, v___x_116_);
lean_ctor_set_uint8(v___x_118_, sizeof(void*)*1, v___x_117_);
v___x_119_ = l_Repr_addAppParen(v___x_118_, v_prec_98_);
return v___x_119_;
}
}
}
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_instReprGrade_repr___boxed(lean_object* v_x_132_, lean_object* v_prec_133_){
_start:
{
uint8_t v_x_171__boxed_134_; lean_object* v_res_135_; 
v_x_171__boxed_134_ = lean_unbox(v_x_132_);
v_res_135_ = lp_BusyBee_BusyBee_instReprGrade_repr(v_x_171__boxed_134_, v_prec_133_);
lean_dec(v_prec_133_);
return v_res_135_;
}
}
static uint8_t _init_lp_BusyBee_BusyBee_instInhabitedGrade_default(void){
_start:
{
uint8_t v___x_138_; 
v___x_138_ = 0;
return v___x_138_;
}
}
static uint8_t _init_lp_BusyBee_BusyBee_instInhabitedGrade(void){
_start:
{
uint8_t v___x_139_; 
v___x_139_ = 0;
return v___x_139_;
}
}
LEAN_EXPORT uint8_t lp_BusyBee_BusyBee_gradeAtMost(lean_object* v_value_140_, lean_object* v_threshold_141_){
_start:
{
uint8_t v___x_142_; 
v___x_142_ = lean_int_dec_le(v_value_140_, v_threshold_141_);
if (v___x_142_ == 0)
{
uint8_t v___x_143_; 
v___x_143_ = 2;
return v___x_143_;
}
else
{
uint8_t v___x_144_; 
v___x_144_ = 0;
return v___x_144_;
}
}
}
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_gradeAtMost___boxed(lean_object* v_value_145_, lean_object* v_threshold_146_){
_start:
{
uint8_t v_res_147_; lean_object* v_r_148_; 
v_res_147_ = lp_BusyBee_BusyBee_gradeAtMost(v_value_145_, v_threshold_146_);
lean_dec(v_threshold_146_);
lean_dec(v_value_145_);
v_r_148_ = lean_box(v_res_147_);
return v_r_148_;
}
}
LEAN_EXPORT uint8_t lp_BusyBee_BusyBee_gradeBps(lean_object* v_value_149_, lean_object* v_threshold_150_){
_start:
{
uint8_t v___x_151_; 
v___x_151_ = lean_int_dec_le(v_value_149_, v_threshold_150_);
if (v___x_151_ == 0)
{
lean_object* v___x_152_; lean_object* v___x_153_; uint8_t v___x_154_; 
v___x_152_ = lean_obj_once(&lp_BusyBee_BusyBee_instReprGrade_repr___closed__6, &lp_BusyBee_BusyBee_instReprGrade_repr___closed__6_once, _init_lp_BusyBee_BusyBee_instReprGrade_repr___closed__6);
v___x_153_ = lean_int_mul(v___x_152_, v_threshold_150_);
v___x_154_ = lean_int_dec_le(v_value_149_, v___x_153_);
lean_dec(v___x_153_);
if (v___x_154_ == 0)
{
uint8_t v___x_155_; 
v___x_155_ = 2;
return v___x_155_;
}
else
{
uint8_t v___x_156_; 
v___x_156_ = 1;
return v___x_156_;
}
}
else
{
uint8_t v___x_157_; 
v___x_157_ = 0;
return v___x_157_;
}
}
}
LEAN_EXPORT lean_object* lp_BusyBee_BusyBee_gradeBps___boxed(lean_object* v_value_158_, lean_object* v_threshold_159_){
_start:
{
uint8_t v_res_160_; lean_object* v_r_161_; 
v_res_160_ = lp_BusyBee_BusyBee_gradeBps(v_value_158_, v_threshold_159_);
lean_dec(v_threshold_159_);
lean_dec(v_value_158_);
v_r_161_ = lean_box(v_res_160_);
return v_r_161_;
}
}
lean_object* initialize_Init(uint8_t builtin);
lean_object* initialize_Init(uint8_t builtin);
void lean_initialize_runtime_module();
static bool _G_initialized = false;
LEAN_EXPORT lean_object* initialize_BusyBee_BusyBee_Common(uint8_t builtin) {
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
lp_BusyBee_BusyBee_instInhabitedGrade_default = _init_lp_BusyBee_BusyBee_instInhabitedGrade_default();
lp_BusyBee_BusyBee_instInhabitedGrade = _init_lp_BusyBee_BusyBee_instInhabitedGrade();
return lean_io_result_mk_ok(lean_box(0));
}
#ifdef __cplusplus
}
#endif
