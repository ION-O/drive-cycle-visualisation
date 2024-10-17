import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
import numpy as np
from data_analysis import load_data, stats_calc, user_power_division, riding_events_power, charge_rate, user_stat
import pybamm

@st.cache_data
def prepare_data():
    filtered_dict_I, data_filtered, dc_all = load_data()

    for df in filtered_dict_I.values():
        df['Power'] = df['Voltage'] * df['Current']

    stats_all = stats_calc(filtered_dict_I)
    # stats_all['Date'] = pd.to_datetime(stats_all['Date'])
    # stats_all['Day of Week'] = stats_all['Date'].dt.day_name()

    user_all = user_stat(dc_all)
    user_all['Date'] = pd.to_datetime(user_all['Date'])
    user_all['Day of Week'] = user_all['Date'].dt.day_name()

    day_behaviour = user_all[["Day of Week", "Drive Cycle ID", "Mean Power [W]"]].copy()
    day_behaviour['ID'] = np.where(day_behaviour['Mean Power [W]'] > 0, 'charge', 'discharge')

    stats_discharge = stats_all[stats_all["Mean Power [W]"] < 0]

    df_temps = stats_discharge[['Drive Cycle ID', 'High_P', 'Medium_P', 'Low_P']]
    violin_df = pd.melt(df_temps, id_vars=['Drive Cycle ID'], 
                        value_vars=['High_P', 'Medium_P', 'Low_P'],
                        var_name='Load Type', value_name='Load')

    return filtered_dict_I, day_behaviour, violin_df, stats_all, user_all


def app():
    st.title('User Behaviour')
    dc_all_fil, data_all, dc_all = load_data()
    cycle_status = {key: 'charge' if (np.mean(df['Current']) >= 0) else 'discharge' for key, df in dc_all.items()}

    # Calculate statistics once
    charge_dict = {k: v for k, v in dc_all.items() if cycle_status[k] == 'charge'}
    discharge_dict = {k: v for k, v in dc_all.items() if cycle_status[k] == 'discharge' and k not in [3, 4]}
    # del discharge_dict[3] # remove the drive cycle with ID 3 as it is an outlier
    # del discharge_dict[4] # remove the drive cycle with ID 4 as it is an outlier
    
    Q_pack = 11

    discharge_fil = {key: df for key, df in discharge_dict.items() if ((df['Current'] <= 1)).all()}
    power_data = np.concatenate([discharge_fil[i]['Power'] for i in discharge_fil])
    current_data = np.concatenate([discharge_fil[i]['Current'] for i in discharge_fil])
    power_data = power_data[power_data < 0]
    current_data = current_data[current_data < 0]

    bins_I, hist_I = user_power_division(current_data, False)
    bins_P, hist_P = user_power_division(power_data, False) 

    # pwr_div = []
    pwr_div = [riding_events_power(dc_all[i], bins_P) for i in dc_all]
    dates = [dc_all[i].DateTime.iloc[0].date() for i in dc_all]
    pwr_df = pd.DataFrame(pwr_div, index=dc_all.keys(), columns=['P_high', 'P_mid', 'P_low', 'P_charge', 'P_total'])
    # power_division = pwr_df.sum(axis=0) / pwr_df.sum(axis=0).P_total
    pwr_percent = pwr_df.div(pwr_df['P_total'], axis=0)
    pwr_percent.drop(columns='P_total', inplace=True)

    pwr_discharge = pwr_percent[pwr_percent.index.isin(discharge_dict.keys())].drop(columns='P_charge')
    # pwr_charge = pwr_df[pwr_df.index.isin(charge_dict.keys())]

    stats_all = stats_calc(dc_all_fil)

    # Preprocess the data
    pwr_df['Date'] = dates
    grouped_data = pwr_df.groupby('Date').sum()[['P_high', 'P_mid', 'P_low', 'P_charge']].reset_index()
    final_data = grouped_data.drop(columns=['Date'])
    final_data['Off'] = 24 * 3600 - final_data.sum(axis=1)

    # Aggregate data for the pie chart
    # discharge_value = sum_data['P_high'] + sum_data['P_mid'] + sum_data['P_low']

    st.write('### Discharge Usage Distribution')
    st.write('We can now begin to investigate the behaviours regarding the charge and discharge profiles closer. The first step of this is to split the power data into three behaviours: High Power, Medium Power, and Low Power. The below histogram presents all of the discharge power data separated into three bins based on the valleys of this data.')
    # Calculate proportions
    # sum_data_per = sum_data / sum_data.sum()

    fig_hist = go.Figure()
    fig_hist.add_trace(go.Histogram(x=power_data, nbinsx=100, histnorm='probability density'))
    fig_hist.update_layout(
        title='Power Distribution',
        xaxis_title='Power [W]',
        yaxis_title='Probability Density',
        height=600,
    )
    # Add vertical line at x = -245
    fig_hist.add_shape(
        type="line",
        x0=bins_P[1][0], x1=bins_P[1][0],  # x-position of the vertical line
        y0=0, y1=0.055,  # y-position (from 0 to max y-axis value)
        line=dict(color="red", width=2, dash="dash")  # Customize line appearance
    )
    fig_hist.add_shape(
        type="line",
        x0=bins_P[2][0], x1=bins_P[2][0],  # x-position of the vertical line
        y0=0, y1=0.055,  # y-position (from 0 to max y-axis value)
        line=dict(color="red", width=2, dash="dash")  # Customize line appearance
    )
    st.plotly_chart(fig_hist, use_container_width=True)

    st.write("Utilising these bins we can now evaluate the individual distribtions within each trip.")

    # User-set values for current categories
    # I_values = {
    #     'High_I': I_bins[0].mean(),
    #     'Medium_I': I_bins[1].mean(),
    #     'Low_I': I_bins[2].mean(),
    #     'Charge_I': 4
    # }
    # fig = go.Figure(data=[go.Pie(labels=['High', 'Medium', 'Low', 'Charge','Off'], values=sum_data[['P_high', 'P_mid', 'P_low', 'P_charge','Off']])])
    # st.plotly_chart(fig, use_container_width=True)

    fig_hist = go.Figure()

    # Add the first trace with bins of size 0.01
    fig_hist.add_trace(go.Histogram(
        x=pwr_discharge['P_high'], 
        histnorm='probability density',
        xbins=dict(
            size=0.01  # Bin width of 0.01
        ), name='High Power'
    ))
    # Add the second trace with bins of size 0.01
    fig_hist.add_trace(go.Histogram(
        x=pwr_discharge['P_mid'], 
        histnorm='probability density',
        xbins=dict(
            size=0.01  # Bin width of 0.01
        ), name='Medium Power'
    ))

    # Add the third trace with bins of size 0.01
    fig_hist.add_trace(go.Histogram(
        x=pwr_discharge['P_low'], 
        histnorm='probability density',
        xbins=dict(
            size=0.01  # Bin width of 0.01
        ), name='Low Power'
    ))
    fig_hist.update_layout(
        title='Power Distribution during Discharge',
        xaxis_title='Proportional Time in Power Category',
        yaxis_title='Probability Density',
        height=600,
        legend_title='Power Category',

    )
    st.plotly_chart(fig_hist, use_container_width=True)


    st.write("Combining this information with the preprocessing data, we can develop a stepped load profile to take in to account this power division. The following pybamm experiment definition presents this load profile.")

    # I_charge = pd.Series([df['Current'].mean() for df in charge_dict.values()]).mean()
    I_charge = np.round(charge_rate(charge_dict)/ Q_pack,1)

    step_per = pwr_discharge.mean(axis=0)
    t_total = 0.5*60*60
    t_h = int(step_per.P_high * t_total)
    t_m = int(step_per.P_mid * t_total)
    t_l = int(step_per.P_low * t_total)

    I_h = np.round(np.abs(np.mean(bins_I[0]))/Q_pack,2)
    I_m = np.round(np.abs(np.mean(bins_I[1]))/Q_pack,2)
    I_l = np.round(np.abs(np.mean(bins_I[2]))/Q_pack,2)

    no_rest_exp = ["Discharge at " + str(I_l) + "C for " + str(t_l) + " seconds or until 2.5 V",
                            "Discharge at " + str(I_m) + "C for " + str(t_m) + " seconds or until 2.5 V",
                            "Discharge at " + str(I_h) + "C for " + str(t_h) + " seconds or until 2.5 V",
                            "Charge at " + str(I_charge) + "C until 4.2 V",
                            "Hold at 4.2 V until 50 mA"
                            ]
    
    formatted_no_rest = ',\n        '.join(f'"{step}"' for step in no_rest_exp)

    st.write("Stepped Load Profile Without Rests:")
    st.markdown(f"""
    ```python
    pybamm.Experiment([(
        {formatted_no_rest}
    )])""")

    if st.button('Run PyBaMM Simulation for Stepped Profile without Rests:'):
        # PyBaMM script that runs when the button is pressed
        model = pybamm.lithium_ion.SPM()  # You can replace this with your specific PyBaMM model
        sim = pybamm.Simulation(model, experiment=pybamm.Experiment(no_rest_exp), solver=pybamm.IDAKLUSolver())
        sol = sim.solve()

        # Step 4: Extract voltage and current
        time = sol["Time [s]"].entries
        current = sol["Current [A]"].entries
        voltage = sol["Terminal voltage [V]"].entries

        # Create a subplot figure with two subplots: one for current and one for voltage
        fig = make_subplots(rows=2, cols=1, subplot_titles=('Current Over Time', 'Voltage Over Time'))

        # Left subplot: Current
        fig.add_trace(go.Scatter(x=time, y=current, mode='lines', name='Current [A]', line=dict(color='blue')), row=1, col=1)

        # Right subplot: Voltage
        fig.add_trace(go.Scatter(x=time, y=voltage, mode='lines', name='Voltage [V]', line=dict(color='red')), row=2, col=1)

        # Update layout for the figure
        fig.update_layout(
            title_text='Current and Voltage Over Time',
            xaxis_title_text='Time [s]',
            height=600,  # Adjust the height to fit the subplots
            showlegend=False
        )

        # Update axis labels for the individual subplots
        fig.update_xaxes(title_text="Time [s]", row=1, col=1)
        fig.update_yaxes(title_text="Current [A]", row=1, col=1)
        fig.update_xaxes(title_text="Time [s]", row=1, col=2)
        fig.update_yaxes(title_text="Voltage [V]", row=1, col=2)

        # Display the plot in Streamlit
        st.plotly_chart(fig, use_container_width=True)
    
    st.write("Stepped Load Profile With Rests:")
    t_total_all = (data_all['DateTime'].iloc[-1] - data_all['DateTime'].iloc[0]).total_seconds()
    t_charge = stats_all[stats_all.index.isin(discharge_dict.keys())]['Duration [s]'].sum()/t_total_all
    t_discharge = (stats_all[stats_all.index.isin(charge_dict.keys())]['Duration [s]'].sum())/t_total_all
    t_off = 1 - t_charge - t_discharge

    t_total = 24 * 3600
    t_dis = t_total * t_discharge
    t_h = int(step_per.P_high * t_dis)
    t_m = int(step_per.P_mid * t_dis)
    t_l = int(step_per.P_low * t_dis)
    t_r = int(t_off * t_total)
    
    rest_exp = [
        "Discharge at " + str(I_l) + "C for " + str(t_l) + "seconds or until 2.5 V",
        "Discharge at " + str(I_m) + "C for " + str(t_m) + "seconds or until 2.5 V",
        "Discharge at " + str(I_h) + "C for " + str(t_h) + "seconds or until 2.5 V",
        "Charge at " + str(I_charge) + "C until 4.2 V",
        "Hold at 4.2 V until 50 mA",
        "Rest for " + str(t_r) + " seconds"]
    
    formatted_rest = ',\n        '.join(f'"{step}"' for step in rest_exp)
    st.markdown(f"""
        ```python
        pybamm.Experiment([(
            {formatted_rest}
        )])""")
    if st.button('Run PyBaMM Simulation for Stepped Profile with Rests:'):

        model = pybamm.lithium_ion.SPM()
        sim = pybamm.Simulation(model, experiment=pybamm.Experiment(rest_exp), solver=pybamm.IDAKLUSolver())

        # Solve the simulation
        sol = sim.solve()

        # Step 4: Extract voltage and current
        time = sol["Time [s]"].entries
        current = sol["Current [A]"].entries
        voltage = sol["Terminal voltage [V]"].entries

        # Create a subplot figure with two subplots: one for current and one for voltage
        fig = make_subplots(rows=2, cols=1, subplot_titles=('Current Over Time', 'Voltage Over Time'))

        # Left subplot: Current
        fig.add_trace(go.Scatter(x=time, y=current, mode='lines', name='Current [A]', line=dict(color='blue')), row=1, col=1)

        # Right subplot: Voltage
        fig.add_trace(go.Scatter(x=time, y=voltage, mode='lines', name='Voltage [V]', line=dict(color='red')), row=2, col=1)

        # Update layout for the figure
        fig.update_layout(
            title_text='Current and Voltage Over Time',
            xaxis_title_text='Time [s]',
            height=600,  # Adjust the height to fit the subplots
            showlegend=False
        )

        # Update axis labels for the individual subplots
        fig.update_xaxes(title_text="Time [s]", row=1, col=1)
        fig.update_yaxes(title_text="Current [A]", row=1, col=1)
        fig.update_xaxes(title_text="Time [s]", row=1, col=2)
        fig.update_yaxes(title_text="Voltage [V]", row=1, col=2)

        # Display the plot in Streamlit
        st.plotly_chart(fig, use_container_width=True)
    


if __name__ == "__main__":
    app()